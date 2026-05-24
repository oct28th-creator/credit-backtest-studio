# Code Review: credit-backtest-studio

> 审查日期：2026-05-24
> 代码库：https://github.com/oct28th-creator/credit-backtest-studio
> 总文件数：58 个源码/项目文件

---

## 目录

- [一、安全漏洞](#一安全漏洞)
- [二、Bug](#二bug)
- [三、数据真实性 —— 指标被硬编码覆盖](#三数据真实性--指标被硬编码覆盖)
- [四、代码质量](#四代码质量)
- [五、性能问题](#五性能问题)
- [六、架构评估](#六架构评估)
- [七、操作建议（按优先级排序）](#七操作建议按优先级排序)

---

## 一、安全漏洞

### 1. [HIGH] API Key 部分泄露 — [ai.py](backend/app/api/ai.py:29-30)

`/api/ai/status` 端点暴露了 `api_key_hint`，显示 DeepSeek API Key 的前 5 个和后 2 个字符：

```python
"api_key_hint": (key[:5] + "…" + key[-2:]) if len(key) > 8 else ("set" if key else "missing"),
```

**风险**：泄露密钥片段降低了暴力破解难度，不应在任何对外接口中暴露密钥信息。

**修复**：移除 `api_key_hint` 字段，仅保留 `api_key_present`（boolean）。

### 2. [MEDIUM] 同步阻塞在异步端点中 — [experiments.py](backend/app/api/experiments.py:317-324)

```python
@router.post("/run")
async def run_experiment(config: ExperimentConfig) -> dict:
    raw = run_backtest(...)  # 同步调用，阻塞整个 event loop
```

`run_backtest()` 包含 NumPy 密集计算和循环操作，在 async 端点中同步执行会阻塞 FastAPI 的 event loop，导致其他请求无法处理。

**修复**：
```python
raw = await asyncio.to_thread(run_backtest, ...)
```

### 3. [MEDIUM] 无速率限制

所有端点均无速率限制保护。`POST /api/experiments/run` 可被反复调用耗尽内存和 CPU（每次 run 生成最多 80k 条合成数据并计算 L1-L5 全部指标）。

**修复**：添加 slowapi 或自定义 rate limit 中间件。

### 4. [LOW] 生产环境 IP 硬编码

[nginx.conf](deploy/nginx.conf:3) 和 [server-setup.sh](deploy/server-setup.sh:3) 中硬编码了 Alibaba Cloud ECS 的公共 IP `8.217.224.101`，降低部署脚本可移植性。

---

## 二、Bug

### 1. [CRITICAL] 部署脚本路径错误 — [server-setup.sh](deploy/server-setup.sh:22-23,32)

```bash
# ❌ 错误 — 实际项目中不存在 app/ 父目录
cd /var/www/credit-backtest-studio/app/backend
pip3 install -r requirements.txt -q

cp /var/www/credit-backtest-studio/app/deploy/nginx.conf /etc/nginx/sites-available/
```

项目实际结构：
```
credit-backtest-studio/
├── backend/          ← 在这里
├── frontend/
├── deploy/           ← 在这里
├── .github/
└── README.md
```

**正确的路径应为**：
```bash
cd /var/www/credit-backtest-studio/backend
cp /var/www/credit-backtest-studio/deploy/nginx.conf /etc/nginx/sites-available/
```

> 此 bug 会导致在全新服务器上执行 `server-setup.sh` 时直接失败。

### 2. [MEDIUM] 分数分布百分比计算错误 — [stability.py](backend/app/services/stability.py:152)

```python
# ❌ vals.sum() 是分数的总和，不是样本数
"pct": round(float(counts[i] / (vals.sum() + 1e-8)), 4),
```

此处用 `vals.sum()`（所有分数的总和）除以单个 bin 的频数，得到的不是真正的分布百分比。应改为：

```python
# ✅ 用样本总数计算百分比
"pct": round(float(counts[i] / len(vals)), 4),
```

### 3. [MEDIUM] 前端 mock 数据与后端不同步

策略定义、拒绝原因分布、RAROC bands、SHAP 权重在以下两个文件中存在两套不同的硬编码数据：

- [fixtures.py](backend/app/data/fixtures.py) — `sample_id: "consumer_2024q1q2"`
- [mockData.ts](frontend/src/data/mockData.ts) — `sample_id: "bf2023"`

修改一端时容易忘记同步另一端，可能导致前后端 dev 模式下行为不一致。

---

## 三、数据真实性 —— 指标被硬编码覆盖

> 关键文件：[fixtures.py](backend/app/data/fixtures.py:370-675)

代码在多个层级调用了 sklearn / scipy 进行真实指标计算，但计算结果在返回前被硬编码的 `targets` 字典覆盖。这使不了解代码的用户误以为看到的是实时计算结果。

### L1：AUC / KS / Lift / Brier — 全部被覆盖

[fixtures.py:370-443](backend/app/data/fixtures.py:370-443)

代码**确实调用了 sklearn/scipy** 进行真实计算：

```python
# Line 381: 真实调用了 roc_auc_score
auc = float(roc_auc_score(y_true, y_pred_prob))
# Line 386: 真实调用了 ks_2samp
ks_stat, _ = stats.ks_2samp(pos_scores, neg_scores)
# Line 389: 真实调用了 brier_score_loss
brier = float(brier_score_loss(y_true, y_pred_prob))
# Line 397: 真实计算了 Lift@20%
lift_at_20 = float(top20_rate / overall_rate)
```

但第 431-443 行，所有结果被硬编码值**直接覆盖**：

```python
targets = {
    "v2.2":      {"ks": 0.42, "auc": 0.78, "lift20": 2.8, "brier": 0.156},
    "v2.3":      {"ks": 0.48, "auc": 0.83, "lift20": 3.2, "brier": 0.142},
    "v2.4-Beta": {"ks": 0.43, "auc": 0.79, "lift20": 2.9, "brier": 0.153},
    "v2.5-RC":   {"ks": 0.45, "auc": 0.81, "lift20": 3.0, "brier": 0.148},
}
if strategy_id in targets:
    t = targets[strategy_id]
    auc = t["auc"]          # ← sklearn 计算结果被丢弃
    ks_stat = t["ks"]       # ← scipy ks_2samp 结果被丢弃
    lift_at_20 = t["lift20"]
    brier = t["brier"]      # ← brier_score_loss 结果被丢弃
```

代码注释给出的理由：
> `raw computation on approved-only subset underestimates discriminative power due to selection bias. Override with business-validated targets.`

**保留了部分真实计算结果**：
- ROC 曲线 (`roc_points`) — 使用 sklearn 真实输出，未被覆盖
- Calibration 校准曲线 (`calib_points`) — 真实计算，未被覆盖
- PSI trend — 基于硬编码的 base 值 + 随机噪声模拟

### L2：Approval Rate / Bad Rate / RAROC — 全部硬编码

[fixtures.py:460-514](backend/app/data/fixtures.py:460-514)

```python
# Line 465-466: 先真实计算了 bad_rate
bad_rate_raw = float(sub["bad"].mean())

# Line 469-481: 全部被覆盖
targets = {
    "v2.2":     {"apr": 0.28, "br": 0.018, "raroc": 0.18},
    "v2.3":     {"apr": 0.38, "br": 0.024, "raroc": 0.22},
    "v2.4-Beta":{"apr": 0.45, "br": 0.032, "raroc": 0.16},
    "v2.5-RC":  {"apr": 0.40, "br": 0.026, "raroc": 0.20},
}
approval_rate = t["apr"]    # ← 硬编码覆盖
bad_rate = t["br"]          # ← 硬编码覆盖
raroc = t["raroc"]          # ← 硬编码覆盖
```

Pareto frontier（帕累托前沿）也是基于这些硬编码值模拟的，并非真实计算。

### L3：Bad Rate / FPD / Roll Rates — 全部硬编码

[fixtures.py:521-569](backend/app/data/fixtures.py:521-569)

```python
bad_rate = t["br"]      # 硬编码
fpd_rate = t["fpd"]     # 硬编码

roll_rates = {          # 全部硬编码
    "m0_to_m1": 0.041,
    "m1_to_m2": 0.58,
    "m2_to_m3plus": 0.65,
}
```

Vintage curve（成熟度曲线）和 FPD monthly trend（首逾月度趋势）是基于这些硬编码值 + 公式/随机噪声生成的，不是真实数据驱动。

### L4：Swap-set — 真实计算，未被覆盖

[fixtures.py:576-632](backend/app/data/fixtures.py:576-632)

L4 的四个象限（double approve / swap-in / swap-out / double reject）的计数和 bad_rate 都来自真实的 `_approve_mask()` 和 `df["bad"]` 数据，**没有任何硬编码覆盖**。这是所有层级中唯一完全使用真实计算结果的层级。

### L5：Fairness — 部分真实，部分覆盖

- DI ratio 的 `_di_ratio()` 函数使用了真实的 approval mask 数据，**大部分是真实计算**
- **但有一处故意覆盖**：[fixtures.py:674-675](backend/app/data/fixtures.py:674-675)

  ```python
  if strategy_id == "v2.4-Beta":
      di_young_core = 0.77  # Override to trigger compliance warning
  ```

- TPR gap 是真实计算
- SHAP feature importance 完全硬编码（在 `compute_shap_feature_importance` 中）

### 总结表

| 层级 | 指标 | 真实计算？ | 被硬编码覆盖？ |
|---|---|---|---|
| **L1** | AUC, KS, Lift, Brier | sklearn/scipy 调用了 | **是，结果被覆盖** |
| **L1** | ROC 曲线, Calibration | sklearn 真实输出 | 否，保留真实结果 |
| **L2** | Approval Rate, Bad Rate, RAROC | 先计算了 | **是，全部覆盖** |
| **L2** | Pareto Frontier | — | 基于硬编码值模拟 |
| **L3** | Bad Rate, FPD, Roll Rates | — | **全部硬编码** |
| **L3** | Vintage, FPD Trend | — | 基于硬编码值 + 公式 |
| **L4** | Swap-set 四象限 | `_approve_mask()` + `df["bad"]` | **否，真实计算** |
| **L5** | DI Ratio | `_di_ratio()` 真实计算 | **仅 v2.4-Beta 被覆盖** |
| **L5** | TPR Gap | 真实计算 | 否 |
| **L5** | SHAP | — | **全部硬编码** |

### 影响评估

1. **策略间相对关系是预设的**：v2.3 的 KS/AUC/RAROC 总是高于 v2.2，无论合成数据如何变化
2. **核心 KPI 不随数据变化**：无论 `generate_synthetic_data` 的参数如何调整，AUC、KS 等值完全不变
3. **对用户具有误导性**：界面呈现的指标看起来像"本次回测结果"，实际是固定的预设值
4. **L4 是例外**：swap-set 分析使用真实数据计算，能反映策略变化对决策一致性的影响

---

## 四、代码质量

### 1. 无用的 pass-through 函数 — [ai.py](backend/app/api/ai.py:80-83)

```python
async def _sse_generator(gen: AsyncGenerator) -> AsyncGenerator[str, None]:
    async for chunk in gen:
        yield chunk
```

该函数只做了一层透传，没有任何转换逻辑。可直接移除，在 `StreamingResponse` 中直接传入原始 generator。

### 2. JSON 解析过于脆弱 — [llm.py](backend/app/services/llm.py:406-409)

```python
if "```json" in json_str:
    json_str = json_str.split("```json")[1].split("```")[0].strip()
```

依赖简单的字符串分割来提取 LLM 返回的 JSON。如果 DeepSeek 返回嵌套代码块或格式异常，容易解析失败（虽有 try/except 兜底，但会丢失 AI 分析结果）。

**建议**：使用正则匹配单个 markdown 代码块，或要求 LLM 以纯 JSON 格式返回（不用 markdown 包裹）。

### 3. 历史查询性能 O(n) — [experiments.py](backend/app/api/experiments.py:379)

```python
for run_id, r in _RUN_STORE.items():
    # 每次都遍历全部历史
```

随着运行次数增加，`GET /history` 响应会越来越慢。建议维护一个预计算的 trend 列表或添加增量更新机制。

### 4. 内存缓存无上限 — [metrics.py](backend/app/services/metrics.py:29)

```python
_DATA_CACHE: dict[tuple, np.ndarray] = {}  # 永不失效
```

缓存在长期运行的服务器上可能累积大量内存。建议使用 `functools.lru_cache(maxsize=...)` 或 `cachetools` 限制最大条目数。

### 5. CORS 配置过于宽松 — [main.py](backend/app/main.py:41-42)

```python
allow_methods=["*"],
allow_headers=["*"],
```

虽然后端通过 `settings.cors_list` 限制了允许的 origin 列表，但 method 和 header 使用通配符仍然过于宽松。建议明确列出需要的方法和请求头。

---

## 五、性能问题

| 文件 | 问题 | 建议 |
|---|---|---|
| [experiments.py](backend/app/api/experiments.py:317) | `run_backtest()` 同步方式运行在 async 端点中，阻塞 event loop | 使用 `asyncio.to_thread()` |
| [metrics.py](backend/app/services/metrics.py:29) | `_DATA_CACHE` 无上限无淘汰策略 | 使用 LRU 缓存 |
| [experiments.py](backend/app/api/experiments.py:379) | `get_history()` 每次遍历全量数据 | 预计算 trend 或增量更新 |
| [metrics.py](backend/app/services/metrics.py:59-63) | 每次 run 都重新应用 slice 和策略 | 考虑并行化 L1-L5 计算 |

---

## 六、架构评估

### 优点

| 方面 | 评价 |
|---|---|
| **关注点分离** | API 层 → Services 层 → Data 层，三层清晰，模块职责明确 |
| **AI 设计理念** | LLM 只做自然语言分析，绝不计算指标。所有数据由后端预计算后传入。这是优秀的安全/准确性设计 |
| **Mock 回退体系** | 前后端均有完整的 mock fallback：后端无 API Key 时返回详细 mock，前端网络失败时使用 mock 数据，支持完全离线开发 |
| **国际化** | 完整的 zh-CN / en 双语支持，通过 i18next 和系统提示词双语实现 |
| **SSE 流式传输** | AI 分析正确使用 Server-Sent Events，支持 thinking tokens 和结果的流式呈现 |
| **Nginx 配置** | 正确配置了 SSE 的无缓冲代理、SPA 路由、gzip 压缩 |
| **测试覆盖** | 50+ 后端单元测试 + 30+ API 集成测试 + 前端单元测试 + Playwright E2E |

### 待改进

| 方面 | 当前状态 | 建议 |
|---|---|---|
| **数据持久化** | 内存 dict (`_RUN_STORE`)，重启丢失 | MVP 可接受，应规划 SQLite/PostgreSQL |
| **认证授权** | 无 | 生产部署前添加 |
| **可观测性** | 仅启动日志，无结构化日志/metrics/tracing | 添加 logging 库 + Prometheus metrics |
| **CI 增强** | GitHub Actions 仅在 push main 时部署，无 PR 校验 | 添加 lint/type-check/test 步骤 |

---

## 七、操作建议（按优先级排序）

| 优先级 | 问题 | 文件 |
|---|---|---|
| **P0 - 立即修复** | 部署脚本路径错误（全新部署将失败） | [server-setup.sh](deploy/server-setup.sh) |
| **P0 - 立即修复** | 移除 `/api/ai/status` 中的 `api_key_hint` | [ai.py](backend/app/api/ai.py:29-30) |
| **P1** | `run_backtest()` 改为线程池执行，避免阻塞 event loop | [experiments.py](backend/app/api/experiments.py:317) |
| **P1** | L1-L3 核心指标被硬编码值覆盖，sklearn 计算结果被丢弃，具有误导性 | [fixtures.py](backend/app/data/fixtures.py:431-569) |
| **P1** | 修复 `compute_score_distribution` 百分比计算 | [stability.py](backend/app/services/stability.py:152) |
| **P2** | 添加速率限制中间件 | 新建 middleware |
| **P2** | 统一前后端 mock 数据或消除重复定义 | [fixtures.py](backend/app/data/fixtures.py) / [mockData.ts](frontend/src/data/mockData.ts) |
| **P2** | 为 `_DATA_CACHE` 添加 LRU 淘汰策略 | [metrics.py](backend/app/services/metrics.py:29) |
| **P3** | 优化 `get_history()` 查询性能 | [experiments.py](backend/app/api/experiments.py:379) |
| **P3** | 改进 JSON 提取逻辑 | [llm.py](backend/app/services/llm.py:406) |
| **P3** | 移除无用的 `_sse_generator` | [ai.py](backend/app/api/ai.py:80-83) |
