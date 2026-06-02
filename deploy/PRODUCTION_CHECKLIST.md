# 生产化上线 Checklist

> 状态:**规划文档,尚未执行**。当前线上仍为单租户演示部署(裸 `http://8.217.224.101`,无鉴权、无 TLS)。
> 本文件汇总把演示部署升级为「可对外」生产部署所需的步骤,大部分对应**已编写但暂未合并的 PR #11**。
>
> ⚠️ 关键风险:PR #11 的若干改动**互相耦合**,且其中 nginx 强制 HTTPS、systemd 专用用户 + venv 会在
> 缺少前置条件(TLS 证书、`server-setup.sh` 重跑)时**打挂当前演示站**。务必按下面顺序、在准备好前置
> 条件后再推进,不要单独把某一项塞进自动部署。

---

## 0. 现状基线(已上线)

- ✅ 安全修复:报告弹窗 XSS、上传 OOM/DoS 上限(25MB)、LLM 输入长度上限、CORS 空值过滤、SQLite WAL、sandbox 还原 bug(PR #12)
- ✅ 可靠性:运行结果持久化到 SQLite + 启动回灌(重启不丢历史 run)、删除数据集清理 parquet(PR #13)
- ✅ CI:`.github/workflows/ci.yml`(PR + main 跑 pytest / 前端 build + vitest)
- ✅ 自动部署:`.github/workflows/deploy.yml`(push main → SCP 前端 + SSH 重启后端)

**尚未上线(本 checklist 覆盖):API 鉴权、HTTPS/TLS、专用服务账户 + venv 隔离、systemd 加固、备份、日志轮转。**

---

## 1. 前置条件(在动任何部署前先备齐)

- [ ] **域名**:为服务器申请一个域名并把 A 记录指向 `8.217.224.101`(Let's Encrypt 不对裸 IP 签证书)
- [ ] **TLS 证书**:服务器上装 certbot —— `apt install certbot python3-certbot-nginx`
- [ ] **`DEEPSEEK_API_KEY`** 已作为 GitHub Secret 配置(部署时写入 `backend/.env`)
- [ ] 决定是否启用 **API 鉴权**(见 §3),若启用需生成一个强随机 `API_KEY`
- [ ] 在服务器上预留一次**维护窗口**(systemd/用户/venv 切换期间后端会短暂重启)

---

## 2. 部署加固(server-setup.sh 一次性,需在服务器手动重跑)

> 这些来自 PR #11 的 `deploy/server-setup.sh` / `backtest-backend.service`,**必须一起**做,因为新的
> systemd 单元用 `User=backtest` + `.venv`,而这两者由 setup 脚本创建。顺序错了会让下次自动部署装上
> 一个起不来的服务。

- [ ] 创建专用非 root 系统用户 `backtest`(无登录 shell)
- [ ] 后端改用项目内 Python virtualenv(`backend/.venv`),避免 PEP 668「externally managed」冲突
- [ ] 安装加固版 `backtest-backend.service`:`NoNewPrivileges` / `ProtectSystem=strict` / `PrivateTmp` /
      `ReadWritePaths=backend/data` / `ProtectHome` 等
- [ ] `systemctl daemon-reload && systemctl restart backtest-backend`,确认 `is-active`
- [ ] 冒烟测试:`curl -fsS http://127.0.0.1:8000/api/samples`
- [ ] 同步更新 `deploy.yml`:venv-aware 的 `pip install`(项目 venv → 新建 venv → 系统 pip 回退)+
      冒烟失败时回滚到上一个 SHA

**操作:** `ssh root@8.217.224.101 'bash -s' < deploy/server-setup.sh`(用 PR #11 版本的脚本)

---

## 3. API 鉴权(可选,默认关闭)

> 来自 PR #11 的 `app/api/deps.py`(`require_api_key`,常量时间比较)。设计为 **opt-in**:不设
> `API_KEY` 环境变量时端点保持开放(演示可用),设了才强制 `X-API-Key`。
> 注意:#12 的 round-3 报告**有意推迟**鉴权,因为无鉴权前端 + 部署冒烟测试都依赖开放端点。

- [ ] 后端:合入 `require_api_key`,挂到 `/api/custom` 与 `/api/ai/*`;`/api/ai/status` 保持公开
- [ ] 后端:`config.py` 增加 `api_key` / `auth_enabled`,从环境变量读取
- [ ] 前端:`VITE_API_KEY` 构建期注入,受保护请求带 `X-API-Key`(`api/client.ts` 的 `authHeaders()`)
- [ ] GitHub Secret 配置 `API_KEY`,部署写入 `backend/.env`,前端构建注入 `VITE_API_KEY`
- [ ] 验证:不带 key → 401;带正确 key → 200;`/api/ai/status` 始终 200
- [ ] **更新 `deploy.yml` 冒烟测试**:若鉴权开启,`curl /api/samples` 需带 key(否则冒烟会误报失败)

---

## 4. HTTPS / TLS(务必在 §1 域名 + 证书就绪后)

> 来自 PR #11 的 `deploy/nginx.conf`:80 → 443 强制跳转,443 启用 ssl。
> 🚨 **不要在没有有效证书时合并这份 nginx 配置** —— 会把所有流量重定向到无证书的 https,演示站直接打不开。

- [ ] 先用 certbot 签发证书:`certbot --nginx -d <你的域名>`(会自动填好 `ssl_certificate*` 行)
- [ ] 合入 PR #11 的 `nginx.conf`(含 80→443 跳转、ACME challenge location、TLS1.2/1.3)
- [ ] `nginx -t && systemctl reload nginx`
- [ ] 验证:`https://<域名>` 正常;`http://<域名>` 301 跳 https;证书链有效
- [ ] 配置 certbot 自动续期(`systemctl status certbot.timer`)

---

## 5. 备份与日志(低风险,可随 §2 一起)

- [ ] 安装 `deploy/backtest-backup.sh`(每日 `sqlite3 .backup`,保留 14 天)到 `/usr/local/bin/` + cron
- [ ] 安装 `deploy/backtest-logrotate` 到 `/etc/logrotate.d/`
- [ ] 验证:手动跑一次备份脚本,确认 `/var/backups/backtest/` 生成 `.db.gz`
- [ ] (可选)把备份同步到异机/对象存储,避免单机磁盘损坏丢数据

---

## 6. 架构级(可延后,非上线必需)

- [ ] **沙箱硬隔离**:`strategies/runner.py` 当前为「演示级」(子进程 + setrlimit + 禁网 + import 白名单,
      但 `exec` 仍持完整 `__builtins__`)。多租户前升级为容器 / `nsjail` / seccomp
- [ ] **DeepSeek client 复用**:`_stream_deepseek` 每次新建 `AsyncOpenAI`,可改单例降低握手开销
- [ ] **前端 bundle 体积**:`index.js` 已超 500KB,考虑动态 import / manualChunks 拆包

---

## 推荐推进顺序

1. §1 备齐前置条件(域名 + 证书最关键)
2. §2 + §5 一起:服务器侧重跑 `server-setup.sh`(专用用户 + venv + systemd 加固 + 备份/日志)
3. §4 HTTPS(证书就绪后再合 nginx 配置)
4. §3 鉴权(最后,且记得同步改 deploy 冒烟测试)

每一步都先在维护窗口内做,做完用 `curl` 冒烟 + 浏览器实测,再进行下一步。PR #11 是这些改动的现成实现,可按上面顺序**拆分**合入,而不是一次性全合。
