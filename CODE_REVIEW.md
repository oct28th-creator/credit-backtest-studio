# Code Review: credit-backtest-studio

> 审查日期：2026-05-24
> 代码库：https://github.com/oct28th-creator/credit-backtest-studio
> 总文件数：58 个源码/项目文件
> 共发现问题 27 项：CRITICAL × 4 / HIGH × 5 / MEDIUM × 10 / LOW × 8

---

## 目录

- [一、安全漏洞](#一安全漏洞)
- [二、Bug](#二bug)
- [三、数据完整性 —— 指标被硬编码覆盖](#三数据完整性--指标被硬编码覆盖)
- [四、代码质量](#四代码质量)
- [五、性能问题](#五性能问题)
- [六、架构与工程实践](#六架构与工程实践)
- [七、操作建议（按优先级排序）](#七操作建议按优先级排序)

---

## 一、安全漏洞

### 1.1 [CRITICAL] 服务以 root 权限运行 — [backtest-backend.service](deploy/backtest-backend.service:7)

```
User=root
```

FastAPI 进程以 root 权限运行。由于 systemd 配置了 `Restart=always`，即使崩溃也会以 root 重启。若 FastAPI 被攻破（如通过注入漏洞），攻击者获得系统完全控制权。虽然后台仅监听 `127.0.0.1:8000`，但与其他漏洞链式利用（SSRF 等）危害极大。

**修复**：创建专用系统用户 `User=backtest`，目录和文件设置最小权限。

### 1.2 [CRITICAL] 无 TLS/SSL 加密传输 — [nginx.conf](deploy/nginx.conf:2)

```
listen 80;
```

仅监听 HTTP 80 端口，无 HTTPS 配置。所有 API 请求（包括 Auth header 中的 DeepSeek API Key）在互联网上明文传输。

**修复**：配置 443 端口 SSL，使用 Let's Encrypt 免费证书，HTTP 强制重定向到 HTTPS。

### 1.3 [CRITICAL] API Key 部分泄露 — [ai.py](backend/app/api/ai.py:29-30)

```python
"api_key_hint": (key[:5] + "…" + key[-2:]) if len(key) > 8 else ...
```

`/api/ai/status` 端点暴露了 DeepSeek API Key 的前 5 个和后 2 个字符，降低了暴力破解难度。不应在任何对外接口中暴露密钥片段。

**修复**：移除 `api_key_hint` 字段，仅保留 `api_key_present`（boolean）。

### 1.4 [HIGH] 同步阻塞在异步端点中 — [experiments.py](backend/app/api/experiments.py:317-324)

```python
@router.post("/run")
async def run_experiment(config: ExperimentConfig) -> dict:
    raw = run_backtest(...)  # 同步调用，阻塞整个 event loop
```

`run_backtest()` 包含 NumPy 密集计算和循环，在 async 端点中同步执行阻塞 FastAPI event loop。

**修复**：`raw = await asyncio.to_thread(run_backtest, ...)`

### 1.5 [HIGH] AI 端点无输入长度限制 — [schemas.py](backend/app/models/schemas.py:41-51)

```python
class AIChatRequest(BaseModel):
    message: str       # ← 无 max_length
    history: list[dict]  # ← 无 max_length

class NLParseRequest(BaseModel):
    text: str          # ← 无 max_length
```

超大输入可导致内存耗尽或 LLM API 费用滥用。可以发送数百万字符的请求体。

**修复**：添加 `max_length` 约束（如 message ≤ 4000, history ≤ 20 条, text ≤ 2000）。

### 1.6 [MEDIUM] 无速率限制

所有端点均无速率限制保护。`POST /api/experiments/run` 可被反复调用耗尽内存和 CPU。

**修复**：添加 slowapi 或自定义 rate limit 中间件。

### 1.7 [LOW] 生产环境 IP 硬编码

[nginx.conf](deploy/nginx.conf:3) 和 [server-setup.sh](deploy/server-setup.sh:3) 中硬编码 `8.217.224.101`。

---

## 二、Bug

### 2.1 [CRITICAL] 部署脚本路径错误 — [server-setup.sh](deploy/server-setup.sh:22-23,32)

```bash
# ❌ 错误 — 项目中没有 app/ 父目录
cd /var/www/credit-backtest-studio/app/backend
pip3 install -r requirements.txt -q

cp /var/www/credit-backtest-studio/app/deploy/nginx.conf /etc/nginx/sites-available/
```

项目实际结构是 `backend/` 和 `deploy/` 在仓库根目录，不存在 `app/` 前缀。正确路径：

```bash
cd /var/www/credit-backtest-studio/backend
cp /var/www/credit-backtest-studio/deploy/nginx.conf /etc/nginx/sites-available/
```

> 此 bug 导致全新服务器上执行 `server-setup.sh` 时直接失败。

### 2.2 [HIGH] 前端 API 路径不匹配（2 处）— [client.ts](frontend/src/api/client.ts:202,231)

**第一处** — [client.ts:202](frontend/src/api/client.ts:202)：
```typescript
// apiFetch 加 /api 前缀 → POST /api/run/{id}/reslice
return await apiFetch<RunResult>(`/run/${runId}/reslice`, ...);
```

后端无 `/api/run/` 前缀的路由。四个路由前缀分别为 `/api/experiments`、`/api/ai`、`/api/samples`、`/api/reports`，无 `/api/run/*` 匹配规则。

**第二处** — [client.ts:231](frontend/src/api/client.ts:231)：
```typescript
// apiFetch 加 /api 前缀 → GET /api/history?...
return await apiFetch<RunHistoryItem[]>(`/history?${qs}`);
```

后端实际路由为 [experiments.py:373](backend/app/api/experiments.py:373)：`GET /api/experiments/history`。前端缺少 `experiments/` 前缀。

> 这两处由于 apiFetch 在 catch 中有 mock fallback，开发/演示中静默降级为 mock 数据，不易察觉。

### 2.3 [HIGH] ExecutionScreen AI 流式竞争条件 — [ExecutionScreen.tsx](frontend/src/screens/ExecutionScreen.tsx:37-84)

```typescript
API.run(config)
  .then(r => { apiResult = r; maybeStartAi(); })
  .catch(() => { apiResult = null; maybeStartAi(); });  // apiResult=null

function maybeStartAi() {
  if (aiStarted || !atAiStep || !apiResult) return;  // null → 直接返回
}
```

动画管线（Load → Score → Metrics → AI）和 API 调用并行执行。若 API 失败且动画已到达 AI 步骤：

1. `apiResult` 为 `null`，`maybeStartAi()` 直接返回
2. AI 步骤动画持续等待，但无任何 AI 调用触发
3. 无错误提示，无重试按钮，页面**永久挂起**

实际触发场景：虽然 `apiFetch` 有 mock fallback，但后端返回 HTTP 200 但 JSON 解析失败时，`API.run` 仍会 reject，触发此路径。

### 2.4 [MEDIUM] 分数分布百分比计算错误 — [stability.py](backend/app/services/stability.py:152)

```python
# ❌ vals.sum() 是分数的总和，不是样本数
"pct": round(float(counts[i] / (vals.sum() + 1e-8)), 4),
```

用 `vals.sum()`（分数总和）除以单个 bin 的频数，得到的不是真正的分布百分比。应改为 `counts[i] / len(vals)`。

### 2.5 [MEDIUM] .gitignore 路径错误 — [.gitignore:16-17](.gitignore:16-17)

```
app/frontend/dist/
app/frontend/.vite/
```

项目无 `app/frontend/` 前缀，实际为 `frontend/dist/` 和 `frontend/.vite/`。这两条规则无效，Vite 构建产物可能被意外提交。

### 2.6 [MEDIUM] reslice 端点后端不存在 — [client.ts:202](frontend/src/api/client.ts:202)

前端调用 `POST /api/run/{id}/reslice`，后端未定义此路由。每次调用都静默降级为 mock。

### 2.7 [LOW] reports.py 未使用的 import — [reports.py:6](backend/app/api/reports.py:6)

```python
import json  # ← 文件中无任何 json.dumps/loads 调用
```

`get_report` 返回 dict 由 FastAPI 自动序列化，`_build_static_report` 构建纯 Markdown 字符串。

---

## 三、数据完整性 —— 指标被硬编码覆盖

> 关键文件：[fixtures.py](backend/app/data/fixtures.py:370-675)

代码在多个层级调用了 sklearn / scipy 进行真实计算，但结果在返回前被硬编码 `targets` 字典覆盖。

### 3.1 L1：AUC / KS / Lift / Brier — 全部被覆盖

[fixtures.py:370-443](backend/app/data/fixtures.py:370-443)

代码确实调用了 sklearn/scipy 进行真实计算：

```python
auc = float(roc_auc_score(y_true, y_pred_prob))        # Line 381
ks_stat, _ = stats.ks_2samp(pos_scores, neg_scores)    # Line 386
brier = float(brier_score_loss(y_true, y_pred_prob))   # Line 389
lift_at_20 = float(top20_rate / overall_rate)           # Line 397
```

但第 431-443 行被硬编码值直接覆盖：

```python
targets = {
    "v2.2":      {"ks": 0.42, "auc": 0.78, "lift20": 2.8, "brier": 0.156},
    "v2.3":      {"ks": 0.48, "auc": 0.83, "lift20": 3.2, "brier": 0.142},
    "v2.4-Beta": {"ks": 0.43, "auc": 0.79, "lift20": 2.9, "brier": 0.153},
    "v2.5-RC":   {"ks": 0.45, "auc": 0.81, "lift20": 3.0, "brier": 0.148},
}
if strategy_id in targets:
    auc = t["auc"]          # ← sklearn 结果被丢弃
    ks_stat = t["ks"]
    lift_at_20 = t["lift20"]
    brier = t["brier"]
```

代码注释：`raw computation on approved-only subset underestimates discriminative power due to selection bias.`

保留了 ROC 曲线和 calibration 曲线的真实计算结果。

### 3.2 L2：Approval Rate / Bad Rate / RAROC — 全部硬编码

[fixtures.py:460-514](backend/app/data/fixtures.py:460-514)

```python
targets = {
    "v2.2":     {"apr": 0.28, "br": 0.018, "raroc": 0.18},
    "v2.3":     {"apr": 0.38, "br": 0.024, "raroc": 0.22},
    "v2.4-Beta":{"apr": 0.45, "br": 0.032, "raroc": 0.16},
    "v2.5-RC":  {"apr": 0.40, "br": 0.026, "raroc": 0.20},
}
approval_rate = t["apr"]    # 硬编码覆盖
bad_rate = t["br"]
raroc = t["raroc"]
```

Pareto frontier 也是基于这些硬编码值模拟的。

### 3.3 L3：Bad Rate / FPD / Roll Rates — 全部硬编码

[fixtures.py:521-569](backend/app/data/fixtures.py:521-569)

所有风险指标（bad_rate、fpd_rate、roll_rates 的 m0m1/m1m2/m2m3）均为硬编码。Vintage curve 和 FPD trend 基于硬编码值 + 公式/噪声生成。

### 3.4 L4：Swap-set — 真实计算

[fixtures.py:576-632](backend/app/data/fixtures.py:576-632)

四个象限的计数和 bad_rate 来自真实的 `_approve_mask()` 和 `df["bad"]`，无硬编码覆盖。

**但是** [experiments.py:210-212](backend/app/api/experiments.py:210-212) 中 reshape 时覆盖了 p_value 和 bad_rate：

```python
"p_value": 0.002,       # ← 硬编码
"base_bad_rate": 3.4,   # ← 硬编码
"swap_out_lift": 2.0,   # ← 硬编码
```

### 3.5 L5：Fairness — 部分真实计算

- DI ratio 大部分通过 `_di_ratio()` 真实计算
- **一处故意覆盖**：[fixtures.py:674-675](backend/app/data/fixtures.py:674-675)
  ```python
  if strategy_id == "v2.4-Beta":
      di_young_core = 0.77  # 触发合规警告
  ```
- TPR gap 真实计算；SHAP feature importance 完全硬编码

### 3.6 总结表

| 层级 | 指标 | 真实计算？ | 被硬编码覆盖？ |
|---|---|---|---|
| L1 | AUC, KS, Lift, Brier | sklearn 调用了 | **是** |
| L1 | ROC 曲线, Calibration | sklearn 真实输出 | 否 |
| L2 | Approval Rate, Bad Rate, RAROC | 先计算了 | **是** |
| L2 | Pareto Frontier | — | 基于硬编码值模拟 |
| L3 | Bad Rate, FPD, Roll Rates | — | **全部硬编码** |
| L3 | Vintage, FPD Trend | — | 基于硬编码值 + 公式 |
| L4 | Swap-set 四象限 | `_approve_mask()` + `df["bad"]` | 否（但 reshape 覆盖 p_value） |
| L5 | DI Ratio | `_di_ratio()` 真实计算 | 仅 v2.4-Beta |
| L5 | TPR Gap | 真实计算 | 否 |
| L5 | SHAP | — | **全部硬编码** |

### 3.7 影响

1. 策略间相对关系预设（v2.3 总是优于 v2.2）
2. 核心 KPI 不随合成数据参数变化
3. 界面指标看起来像「本次回测结果」，实际是固定预设值
4. L4 swap-set 是唯一反映策略变更影响真实计算的层级

---

## 四、代码质量

### 4.1 无结构化日志 — [main.py](backend/app/main.py:17-23)

整个后端仅使用 `print()` 输出，无时间戳、日志级别、模块名。生产环境完全缺乏可观测性。

**修复**：使用 Python `logging` 模块或 `structlog`。

### 4.2 layers 字段是 untyped dict — [schemas.py](backend/app/models/schemas.py:27)

```python
layers: dict  # L1-L5 computed results
```

Pydantic 模型的字段无类型参数，IDE 和 mypy 无法提供类型检查。

### 4.3 `_RUN_STORE` 跨模块紧耦合

[ai.py:16](backend/app/api/ai.py:16) 和 [reports.py:9](backend/app/api/reports.py:9) 均直接导入：

```python
from app.api.experiments import _RUN_STORE
```

两个模块直接引用 `experiments.py` 的模块级私有 dict。换成数据库需同时改三处。

### 4.4 pip 全局安装 — [server-setup.sh:23](deploy/server-setup.sh:23)

```bash
pip3 install -r requirements.txt -q
```

无 `--user` 或 virtualenv，依赖安装到系统级 Python。多项目共存时易引发冲突。

### 4.5 CORS 配置过于宽松 — [main.py](backend/app/main.py:41-42)

```python
allow_methods=["*"],
allow_headers=["*"],
```

虽然后端通过 `cors_list` 限制了 origin，但 method 和 header 使用通配符过于宽松。

### 4.6 JSON 解析过于脆弱 — [llm.py](backend/app/services/llm.py:406-409)

```python
json_str = json_str.split("```json")[1].split("```")[0].strip()
```

依赖简单字符串分割，LLM 返回嵌套代码块或格式异常时解析失败（虽有兜底但丢失 AI 结果）。

### 4.7 language 字段未使用 Literal 类型 — [schemas.py](backend/app/models/schemas.py:15,38,46,51)

```python
language: str = "zh"  # 应为 Literal["zh", "en"]
```

Pydantic 无法在编译期校验非法语言代码。

### 4.8 fairness 代码重复 — [fairness.py](backend/app/services/fairness.py) / [fixtures.py](backend/app/data/fixtures.py)

`compute_fairness_report()` 和 `_compute_l5()` 各自实现了相同的 DI ratio、TPR gap 计算逻辑，存在大量重复代码。

### 4.9 前端 mock 数据与后端不同步

策略定义、拒绝原因等在 [fixtures.py](backend/app/data/fixtures.py) 和 [mockData.ts](frontend/src/data/mockData.ts) 中存在两套硬编码（如 `sample_id`：后端 `consumer_2024q1q2` vs 前端 `bf2023`）。

### 4.10 策略颜色硬编码 — [mockData.ts](frontend/src/data/mockData.ts) / [stratColors.ts](frontend/src/stratColors.ts)

策略颜色在 `STRAT_COLORS` 和 `stratColors` 中重复定义，[StratChip.tsx](frontend/src/components/StratChip.tsx) 和 [Chart.tsx](frontend/src/components/Chart.tsx) 各自使用。

### 4.11 `__init__.py` 空文件（6 个）

```
app/__init__.py          0 B
app/api/__init__.py      0 B
app/data/__init__.py     0 B
app/models/__init__.py   0 B
app/services/__init__.py  0 B
tests/__init__.py        0 B
```

全部 0 字节，无 docstring 也无 `__all__` 导出声明。

### 4.12 无用的 pass-through 函数 — [ai.py](backend/app/api/ai.py:80-83)

```python
async def _sse_generator(gen):
    async for chunk in gen:
        yield chunk
```

纯透传，可移除，`StreamingResponse` 中直接传入原始 generator。

---

## 五、性能问题

### 5.1 [HIGH] 同步阻塞 event loop — [experiments.py](backend/app/api/experiments.py:317)

`run_backtest()` 同步运行在 async 端点中。见安全漏洞 1.4。

### 5.2 [MEDIUM] 内存缓存无上限 — [metrics.py](backend/app/services/metrics.py:29)

```python
_DATA_CACHE: dict[tuple, np.ndarray] = {}  # 永不失效
```

长期运行可能累积大量内存。建议使用 `functools.lru_cache(maxsize=...)`。

### 5.3 [MEDIUM] 分页全量拷贝 O(n) — [experiments.py](backend/app/api/experiments.py:353)

```python
runs = list(reversed(list(_RUN_STORE.values())))  # 先全量拷贝
```

应先按时间排序再切片，或维护排序索引。

### 5.4 [LOW] AI 端点无连接超时

所有 SSE streaming 端点无 `keep_alive_timeout` 或连接数限制。

### 5.5 历史查询 O(n) 遍历 — [experiments.py](backend/app/api/experiments.py:379)

每次 `GET /history` 遍历全部 `_RUN_STORE`。

---

## 六、架构与工程实践

### 优点

| 方面 | 评价 |
|---|---|
| 关注点分离 | API → Services → Data 三层清晰 |
| AI 设计理念 | LLM 只做自然语言分析，不计算指标（安全/准确性保障） |
| Mock 回退体系 | 前后端完整 mock fallback，支持离线开发 |
| 国际化 | 完整 zh-CN / en 双语支持 |
| SSE 流式 | AI 分析正确使用 SSE 流式传输 |
| Nginx 配置 | SSE 无缓冲代理、SPA 路由、gzip 均配置正确 |
| 测试覆盖 | 50+ 后端单元测试 + 30+ API 集成测试 + 前端单元 + Playwright E2E |

### 待改进

| 方面 | 当前 | 建议 |
|---|---|---|
| 权限控制 | root 运行 | 专用用户 + 最小权限 |
| 传输安全 | HTTP 明文 | HTTPS + Let's Encrypt |
| 数据持久化 | 内存 dict，重启丢失 | SQLite/PostgreSQL |
| 认证授权 | 无 | 生产部署前添加 |
| 可观测性 | `print()` 日志 | logging + Prometheus metrics |
| CI 增强 | 仅 push main 部署 | 添加 PR lint/type-check/test |
| 前端容错 | 无 ErrorBoundary | 添加 React Error Boundary |
| 健康检查 | 返回静态 dict | 检查关键依赖可达性 |

---

## 七、操作建议（按优先级排序）

| 优先级 | 问题 | 文件 |
|---|---|---|
| **P0** | 部署脚本路径全部错误 | [server-setup.sh](deploy/server-setup.sh) |
| **P0** | 服务以 root 运行 | [backtest-backend.service](deploy/backtest-backend.service) |
| **P0** | 移除 `/api/ai/status` 中的 `api_key_hint` | [ai.py](backend/app/api/ai.py) |
| **P0** | 配置 HTTPS + Let's Encrypt | [nginx.conf](deploy/nginx.conf) |
| **P1** | 前端 API 路径不匹配（2 处），静默降级为 mock | [client.ts](frontend/src/api/client.ts) |
| **P1** | run_backtest() 改为线程池执行 | [experiments.py](backend/app/api/experiments.py) |
| **P1** | L1-L3 核心指标被硬编码覆盖 | [fixtures.py](backend/app/data/fixtures.py) |
| **P1** | AI 端点添加输入长度限制 | [schemas.py](backend/app/models/schemas.py) |
| **P1** | ExecutionScreen 竞争条件修复 | [ExecutionScreen.tsx](frontend/src/screens/ExecutionScreen.tsx) |
| **P1** | 修复 compute_score_distribution 百分比计算 | [stability.py](backend/app/services/stability.py) |
| **P2** | 添加速率限制中间件 | 新建 middleware |
| **P2** | 修复 .gitignore 路径 | [.gitignore](.gitignore) |
| **P2** | 添加结构化日志 | [main.py](backend/app/main.py) |
| **P2** | _DATA_CACHE 添加 LRU 淘汰策略 | [metrics.py](backend/app/services/metrics.py) |
| **P2** | layers 字段使用 TypedDict 或 Pydantic 模型 | [schemas.py](backend/app/models/schemas.py) |
| **P2** | _RUN_STORE 解耦（抽取为独立模块） | experiments / ai / reports |
| **P3** | 统一前后端 mock 数据 | fixtures.py / mockData.ts |
| **P3** | 优化 history 查询性能 | [experiments.py](backend/app/api/experiments.py) |
| **P3** | 改进 JSON 提取逻辑 | [llm.py](backend/app/services/llm.py) |
| **P3** | pip 安装用 virtualenv | [server-setup.sh](deploy/server-setup.sh) |
| **P3** | language 字段使用 Literal 类型 | [schemas.py](backend/app/models/schemas.py) |
| **P3** | 消除 fairness 代码重复 | fairness.py / fixtures.py |
| **P3** | 添加 React ErrorBoundary | App.tsx / 新建组件 |
| **P3** | health check 检查外部依赖 | [main.py](backend/app/main.py) |
| **P3** | 移除未使用的 import | [reports.py](backend/app/api/reports.py) |
