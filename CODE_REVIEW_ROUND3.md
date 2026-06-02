# 三次代码 Review 报告

**项目**: credit-backtest-studio
**Review 范围**: `claude/happy-pascal-AuONv` 分支，基于 `f5ead52` 的完整代码库
**Review 日期**: 2026-05-30
**Review 方法**: 全量走查 backend（Python/FastAPI）、frontend（React/TypeScript/Vite）、deploy（systemd/CI），并实现高置信度修复
**Review 风格**: 沿用外部报告的 Critical / Warning / Suggestion / Architecture 分级 + 评分

---

## 0. 缘起说明

本轮的触发输入是一份针对 `ai-driven-quant-research-assistant`（Flask + 原生 JS 的量化交易机器人）的
Review 报告。该报告引用的文件（`web/services.py`、`engine.py`、`market_data.py`、`news.py`、
`ai_analyst.py`、`runtime_store.py`、`app.js` 等）在本仓库**均不存在** —— 本仓库是 FastAPI + React
的信贷回测平台。因此 C1–C4 / W1–W8 等条目**无法逐条套用**。

经与需求方确认，本轮按"同样的 Review 风格"对 **credit-backtest-studio** 重做一遍，并落地真实存在的
Critical / Warning 级问题的修复。下文所有条目均为本仓库的真实问题。

---

## 1. Critical（严重）—— 本 PR 已修复

### C1. [security] 报告弹窗 XSS：`dangerouslySetInnerHTML` + 未转义 Markdown

**文件**: `frontend/src/components/ReportModal.tsx:48`（`renderMd`）

`renderMd()` 仅做了 Markdown 标记替换，**没有对原始 HTML 转义**，其输出直接喂给
`dangerouslySetInnerHTML`。报告正文 `content` 来自 LLM 流式输出，而 LLM 的 facts 中可能混入用户可控
内容（如上传策略/数据集的 `name`、`version`），存在**提示注入 → DOM XSS**的链路：注入
`<img src=x onerror=alert(document.cookie)>` 即可在受害者浏览器执行。

**修复**: 在 Markdown 变换前先转义 `&`、`<`、`>`，使任何原始标记被当作文本渲染；保留 `#`/`**`/`*`
等 Markdown 语义不受影响。

### C2. [reliability] 数据集上传先全量读入内存再做行数截断 → OOM/DoS

**文件**: `backend/app/api/custom.py:77`（`create_dataset`）

旧逻辑 `raw = await file.read()` 把整份上传**无上限**读入内存，随后才 `pd.read_csv` 并按
`_MAX_ROWS=80000` 截断。在 2 核 2G 的目标机上，一个几百 MB 的 CSV 在 `read()` + DataFrame 构造阶段
即可耗尽内存（行数上限在此之后才生效，形同虚设）。

**修复**: 读取上限 `_MAX_UPLOAD_BYTES = 25MB`（对 8 万行书足够宽裕），超限直接返回 `413`，在 pandas
落地前拦截。

---

## 2. Warnings（警告）—— 本 PR 已修复

### W1. [reliability] SQLite 未启用 WAL → "database is locked"

**文件**: `backend/app/db/engine.py:14`（`get_conn`）

默认 `journal_mode=delete`。引擎写 `runs` 表与多个只读端点（`/custom/*`）经由 `check_same_thread=False`
的短连接并发读写同一 DB，存在 `database is locked` 风险。

**修复**: 每个连接启用 `PRAGMA journal_mode=WAL` + `busy_timeout=5000` + `synchronous=NORMAL`。

### W2. [security] LLM/上传输入无长度上限 → token 滥用 / 超大第三方请求

**文件**: `backend/app/models/schemas.py`、`backend/app/services/llm.py:559`

`AIChatRequest.message` / `history`、`NLParseRequest.text`、`StrategyUpload.code` 均无上限，用户可构造
超长 prompt 消耗 DeepSeek 配额或触发 API 错误。

**修复**: 在 schema 上加 `Field(max_length=...)`（message/text 4000、code 200KB、history 50 条）；并在
`stream_chat` 组装消息时对每条 content 再做 4000 字截断（纵深防御，因为请求会发往不可控的第三方 API）。

### W3. [correctness] `cors_list` 未过滤空串

**文件**: `backend/app/config.py:15`

`cors_origins.split(",")` 在末尾逗号或空值时会产出 `""`，被 `CORSMiddleware` 当作真实来源。

**修复**: 过滤空白项。同时将已废弃的 `class Config` 迁移为 `SettingsConfigDict`（消除 pydantic v2
DeprecationWarning）。

### W4. [correctness] 沙箱 `socket` 还原捕获了打补丁后的桩函数（潜在 bug）

**文件**: `backend/app/strategies/runner.py:_install_guards`

旧代码先 `socket.socket = _no_socket` 再 `real_socket = socket.socket`，导致 `real_socket` 捕获的是
桩函数；`_restore()` 还原的也就不是真正的 socket。当前子进程一次性退出，影响被掩盖，但属逻辑错误。

**修复**: 在打补丁**之前**先捕获真实 `socket.socket` 与 `__import__`。

---

## 3. Suggestions（建议）

### S1. [CI] 仅有部署 workflow，无测试/类型检查 —— 本 PR 已修复

`.github/workflows/deploy.yml` 仅在推送 `main` 时部署，**不跑任何测试**。

**修复**: 新增 `.github/workflows/ci.yml`（PR + main）：backend 安装依赖跑 `pytest`，frontend `npm ci` +
`npm run build`（含 `tsc` 类型检查）+ `npm test`（vitest）；新增 `backend/requirements-dev.txt`。

### S2. [security] 所有 API 端点无鉴权 —— 暂未改动（设计取舍）

`main.py` 仅配置 CORS，无任何认证。当前为单租户演示部署（绑定固定服务器 IP），且无鉴权的前端与部署
冒烟测试 `curl /api/samples` 都依赖于此。**贸然加鉴权会破坏前端与部署**，故本轮不改。

**建议**: 若将来对公网暴露，应在反代层加 Basic Auth / 网关令牌，或在 FastAPI 加可选的
`Depends` 令牌校验（用 `hmac.compare_digest` 比较）。

### S3. [security] 策略沙箱为"演示级"，非硬隔离边界 —— 暂未改动（既定设计）

`runner.py` 已在 docstring 中**诚实声明**其威胁模型：子进程 + `setrlimit` + 禁网 + `__import__` 白名单，
但 `exec` 仍持有完整 `__builtins__`，无法防住有意为之的 Python 内省逃逸。

**建议**: 多租户前应升级为 OS 级隔离（容器 / `nsjail` / seccomp）。本轮保持原设计，仅修复 W4 的还原 bug。

---

## 4. Architecture（架构级，未改动，供后续规划）

- **O1. `_RUN_STORE` 为纯内存**：`run_experiment` 虽然也写入 SQLite `runs` 表，但启动时**不回灌**
  `_RUN_STORE`，进程重启后历史 run 经 `/api/experiments/{id}` 与所有 AI 端点查询会 404。建议启动时从
  SQLite 水合，或让查询在内存未命中时回退到 `repository.get_run`。
- **O2. 沙箱硬隔离**：见 S3。
- **O3. HTTP 客户端复用**：`_stream_deepseek` 每次新建 `AsyncOpenAI`。可复用单例 client 降低握手开销。

---

## 5. 验证

- 后端：`pytest -q` → **102 passed**（修复前后一致，无回归）。
- 前端：`npm run build`（tsc 类型检查）+ `npm test`（vitest）经新增 CI 覆盖。
- 改动均为最小侵入式，未触碰指标计算、reshape、前端图表等核心逻辑。

---

## 6. 评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 代码质量 | 8/10 | 模块边界清晰、注释充分、设计约束明确 |
| 测试覆盖 | 7/10 | 102 个测试覆盖 API 与指标；上传/沙箱执行路径缺直接用例 |
| 安全性 | 7/10 | 修复 XSS/输入上限后明显改善；鉴权缺失与沙箱演示级为已知取舍 |
| 可靠性 | 8/10 | WAL + 上传上限修复后并发与 OOM 风险下降；`_RUN_STORE` 易失为已知项 |
| 可维护性 | 8/10 | 命名规范、house-style 文档齐全、新增 CI |
| 性能 | 8/10 | 2C/2G 约束下 `asyncio.to_thread` + LRU 缓存设计合理 |
| **总体** | **7.7/10** | 设计良好的演示级平台；本轮已闭合 C1–C2 / W1–W4 与 CI 缺口 |
