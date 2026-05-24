# Credit Backtest Studio 代码审查报告 (合并版)

> **审查日期**：2026-05-24
> **代码库**：`/Users/lin/Documents/Qoder/credit-backtest-studio`
> **涉及模块**：FastAPI 后端、React 前端、部署脚本
> **评估结论**：原 `CODE_REVIEW.md` 中指出的所有问题 **100% 真实存在**。此外，我们还发现了一个非常致命的隐藏缺陷 —— **后端缺失重新切片（Reslice）接口**。

---

## 目录
- [一、安全漏洞](#一安全漏洞)
- [二、关键缺陷（Bugs）](#二关键缺陷bugs)
- [三、数据真实性问题 —— 指标硬编码覆盖](#三数据真实性问题--指标硬编码覆盖)
- [四、性能瓶颈](#四性能瓶颈)
- [五、代码质量与可维护性](#五代码质量与可维护性)
- [六、架构评估](#六架构评估)
- [七、操作建议与优先级](#七操作建议与优先级)

---

## 一、安全漏洞

### 1. [HIGH] API Key 提示信息部分泄露
- **位置**：[ai.py:L29-L30](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/ai.py#L29-L30)
- **详情**：
  `/api/ai/status` 诊断端点返回了 `api_key_hint`。该字段输出了 DeepSeek API Key 的前 5 位和后 2 位字符：
  ```python
  "api_key_hint": (key[:5] + "…" + key[-2:]) if len(key) > 8 else ("set" if key else "missing"),
  ```
- **风险**：暴露密钥片段显著降低了 API Key 的破解难度，不应在任何对外接口中暴露密钥信息。
- **修复方案**：移除 `api_key_hint` 字段，仅保留布尔类型的 `api_key_present`。

### 2. [MEDIUM] 接口无速率限制（Rate Limiting）
- **位置**：后端路由全局配置 [main.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/main.py)
- **详情**：平台支持多次运行回测，每次运行涉及最多 80k 条数据的指标计算（L1-L5）。反复请求 `POST /api/experiments/run` 会导致 CPU 和内存被快速耗尽。
- **修复方案**：引入 `slowapi` 等限流中间件，对高消耗计算端点限速。

### 3. [LOW] 生产环境配置硬编码与宽松 CORS
- **位置**：
  - [nginx.conf:L3](file:///Users/lin/Documents/Qoder/credit-backtest-studio/deploy/nginx.conf#L3) 和 [server-setup.sh:L3](file:///Users/lin/Documents/Qoder/credit-backtest-studio/deploy/server-setup.sh#L3) 中硬编码了公网 IP `8.217.224.101`，影响部署可移植性。
  - [main.py:L41-L42](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/main.py#L41-L42) CORS 配置过于宽松（允许所有 Method 和 Header）。

---

## 二、关键缺陷（Bugs）

### 1. [CRITICAL] 部署脚本路径包含不存在的 `app/` 目录
- **位置**：[server-setup.sh:L22-L23](file:///Users/lin/Documents/Qoder/credit-backtest-studio/deploy/server-setup.sh#L22-L23) 及多处路径
- **详情**：
  部署脚本中使用 `/var/www/credit-backtest-studio/app/...` 路径切换目录或复制配置。但实际项目中并没有 `app` 子目录，`backend` 和 `deploy` 目录直接位于项目根目录下。
- **后果**：直接在服务器上执行 `server-setup.sh` 时，会导致目录切换失败，部署直接中断。
- **修复方案**：将脚本中所有 `/var/www/credit-backtest-studio/app/` 替换为 `/var/www/credit-backtest-studio/`。

### 2. [CRITICAL] 【新增发现】后端缺失重新切片 (Reslice) 接口
- **位置**：[client.ts:L202](file:///Users/lin/Documents/Qoder/credit-backtest-studio/frontend/src/api/client.ts#L202) 和后端 API
- **详情**：
  前端切换切片过滤维度时，会通过 API 客户端请求 `/api/run/{run_id}/reslice`，但在 FastAPI 后端中，**没有任何路由实现了这个端点**。这使得每次在界面更改过滤切片时，请求必然抛出 404 错误，并触发前端静默回退：
  ```typescript
  // client.ts L200
  async reslice(runId: string, sliceConfig: { slice_dim: string | null; slice_value: string | null }): Promise<RunResult> {
    try {
      return await apiFetch<RunResult>(`/run/${runId}/reslice`, { method: 'POST', body: JSON.stringify(sliceConfig) });
    } catch {
      return applyMockSlice(MOCK_RUN_RESULT, sliceConfig); // 404 失败后静默回退
    }
  }
  ```
- **后果**：用户切换数据切片时，页面展示的实际上是前端随机模拟出来的 mock 结果，并不是后端真实数据的计算切片，造成严重的结论失真。
- **修复方案**：在后端 `experiments.py` 中挂载该路由，实现根据已完成回测的配置重新读取样本数据、执行 `_apply_slice` 过滤、重算指标并返回新的 `RunResult`。

### 3. [MEDIUM] 信用分分布百分比计算错误
- **位置**：[stability.py:L152](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/services/stability.py#L152)
- **详情**：
  在计算分箱百分比时：
  ```python
  "pct": round(float(counts[i] / (vals.sum() + 1e-8)), 4),
  ```
  `vals.sum()` 累加了所有信用评分值（如 680 + 720...），而不是样本行数 `len(vals)`。
- **后果**：导致输出的百分比 `pct` 变得极小，前端直方图展示异常。
- **修复方案**：将 `vals.sum()` 修改为 `len(vals)`。

### 4. [MEDIUM] 前端 mock 数据与后端定义不同步
- **位置**：[fixtures.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/data/fixtures.py) vs [mockData.ts](file:///Users/lin/Documents/Qoder/credit-backtest-studio/frontend/src/data/mockData.ts)
- **详情**：
  策略定义参数、数据集定义（后端主样本为 `consumer_2024q1q2`，前端 mock 为 `bf2023`）及风险指标在两端分别硬编码，导致行为与呈现的不一致。
- **修复方案**：统一静态配置并维护相同的字段值映射。

---

## 三、数据真实性问题 —— 指标硬编码覆盖

> [!IMPORTANT]
> **核心问题**：为了修正选择性偏差（Selection Bias），代码虽然真实调用了 `sklearn` 和 `scipy`，但大量核心结果在返回前被硬编码的预设 targets 覆盖了（[fixtures.py:L370-L675](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/data/fixtures.py#L370-L675)）。

### 各层级覆盖情况详情

| 层级 | 指标名称 | 是否真实计算 | 覆盖情况 |
|---|---|---|---|
| **L1: 模型质量** | AUC, KS, Lift@20%, Brier | 仅计算，但输出被覆盖 | **被覆盖**。最终输出均来自硬编码（如 v2.3 固定为 KS=0.48, AUC=0.83）。仅保留了真实计算的 ROC/Calibration 曲线。 |
| **L2: 业务价值** | 通过率, 坏账率, RAROC | 是 | **被覆盖**。Pareto 前沿也是基于硬编码值加上随机公式模拟的，无法体现真实数据的变化。 |
| **L3: 风险指标** | 坏账率, FPD率, 滚动率 | 否 | **完全硬编码**。Vintage 曲线也是基于固定指标套用 logistic 公式模拟生成。 |
| **L4: 决策一致性** | 换入/换出四象限统计 | 是 | **否 (完全真实)**。这是唯一完全用真实策略和坏账数据算出的层级。 |
| **L5: 公平性合规** | 差异影响比率 (DI Ratio) | 是 | **部分覆盖**。仅对 `v2.4-Beta` 的年轻客群 DI 覆盖重写为 `0.77` 以强行触发合规警告，其余组别为真实计算。SHAP 特征重要性则为完全硬编码。 |

- **改造建议**：
  1. 引入正式的拒绝推断算法（如 Parceling 或者是双变量 Probit）来科学修正偏差。
  2. 显式暴露出“原始计算结果”与“拒绝推断修正指标”的开关，禁止隐式硬编码覆盖。

---

## 四、性能瓶颈

### 1. [MEDIUM] 密集计算同步调用阻塞事件循环
- **位置**：[experiments.py:L317](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/experiments.py#L317)
- **详情**：在异步路由 `run_experiment` 里同步调用 CPU 密集型的 NumPy 计算 `run_backtest`，将导致 FastAPI 主线程被独占阻塞数秒，在此期间其他所有用户的请求都无法被接受 and 响应。
- **修复方案**：改为线程池调用：`raw = await asyncio.to_thread(run_backtest, ...)`。

### 2. [MEDIUM] 缓存 `_DATA_CACHE` 缺少容量上限与驱逐
- **位置**：[metrics.py:L29](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/services/metrics.py#L29)
- **详情**：全局缓存字典 `_DATA_CACHE` 会永久驻留生成的样本数组，当生成多次不同种子的样本时，会不断积攒内存最终触发 OOM。
- **修复方案**：使用 `cachetools.LRUCache` 或限制最大条目数的 `lru_cache`。

### 3. [LOW] 历史记录查询复杂度 O(N)
- **位置**：[experiments.py:L379](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/experiments.py#L379)
- **详情**：`GET /api/experiments/history` 会每次执行全表扫描重塑结果。随着实验增多，该接口响应速度会显著变慢。

---

## 五、代码质量与可维护性

### 1. 无用的透传生成器
- **位置**：[ai.py:L80-L83](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/ai.py#L80-L83)
- **详情**：`_sse_generator` 只做了一层 `yield` 循环转发，无任何数据转换或处理逻辑。建议直接移除，精简调用链。

### 2. 脆弱的 JSON 解析逻辑
- **位置**：[llm.py:L406-L409](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/services/llm.py#L406-L409)
- **详情**：依赖简单的 `"```json"` 字符串分割逻辑提取 DeepSeek 返回的 JSON 块。一旦模型输出格式存在微调（如缺少反单引号、包含前置干扰文本），就会导致解析出错回退到默认数据。
- **修复方案**：编写基于正则表达式的 JSON 提取工具类。

---

## 六、架构评估

### 1. 优势
- **三层架构设计清晰**：Controller (API) -> Service -> Data (Fixtures) 层级划分鲜明。
- **AI 幻觉规避极佳**：设计原则坚持 **AI 不参与任何指标的算术计算**，只做预计算结果的自然语言提炼，极其符合信贷系统的安全严谨要求。
- **流式体验配置完善**：对 SSE 响应以及 Nginx 代理关闭缓冲（`proxy_buffering off`）支持到位。

### 2. 劣势
- **持久化缺失**：使用内存存储，后端重启导致实验数据清空。
- **可观测性弱**：没有结构化日志及 Prometheus 指标监控。

---

## 七、操作建议与优先级

| 优先级 | 缺陷描述 | 涉及文件 | 修复动作建议 |
|---|---|---|---|
| **P0 - 阻断** | 部署脚本包含错误路径 `/app/`，致部署失败 | [server-setup.sh](file:///Users/lin/Documents/Qoder/credit-backtest-studio/deploy/server-setup.sh) | 移除 `/app/` 并更改为项目实际绝对路径 |
| **P0 - 阻断** | 重新切片 (Reslice) 后端接口 404，完全失效 | [experiments.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/experiments.py) | 实现重新切片的后台计算与接口挂载 |
| **P0 - 阻断** | `api_key_hint` 导致 API Key 泄漏 | [ai.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/ai.py) | 彻底删除 status 端点中的 hint 返回 |
| **P1 - 严重** | 信用分直方图百分比分母使用 `vals.sum()` 错误 | [stability.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/services/stability.py) | 将 `vals.sum()` 改为 `len(vals)` |
| **P1 - 严重** | 回测计算阻塞 FastAPI 事件循环 | [experiments.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/experiments.py) | 引入 `asyncio.to_thread` 或者是 Celery 异步处理 |
| **P1 - 严重** | L1-L3 指标被预设 targets 覆盖，非真实反馈 | [fixtures.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/data/fixtures.py) | 移除强制 targets 覆盖或实现拒绝推断开关 |
| **P2 - 中等** | `_DATA_CACHE` 无限制增长，内存泄露 | [metrics.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/services/metrics.py) | 添加 LRU 缓存策略，限制样本最大存储个数 |
| **P2 - 中等** | 前后端 mock 字段与定义冲突 | `fixtures.py` / `mockData.ts` | 统一策略以及样本属性的定义，避免逻辑分叉 |
| **P3 - 优化** | JSON 解析脆弱、冗余透传生成器 | `llm.py` / `ai.py` | 优化正则 JSON 抽取，移除无用的生成器包装 |
