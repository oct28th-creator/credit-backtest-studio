# Credit Backtest Studio → Agentic 实验 / 分析 / 仿真平台 升级方案

> 版本：v1.0（2026-09）
> 适用代码基线：`main` @ 提交 `31b6606`（FastAPI + React 18，L1–L5 指标体系，DeepSeek SSE 解读）
> 本文档 = 现状盘点 → 差距 → 目标架构 → 接口契约 → 分阶段路线。P1 骨架代码已随本分支提交。

---

## 0. 一句话结论

现有系统是**「人提假设 → 系统算一次 → AI 讲解结果」**；要变成 agentic 实验/仿真平台，缺的不是模型能力，而是**实验的身份、不可变性、可控性、可观测性和记忆**这五件基础设施。
指标层（L1–L5）、策略沙箱、自定义数据集/列映射这三块资产可以 100% 复用，是这个项目最值钱的部分。

---

## 1. 现状盘点（代码级）

| 模块 | 现状 | 评价 |
|---|---|---|
| 数据层 `app/data/fixtures.py` | 合成账簿生成器（≤80k 行，`seed=42` 固定），4 个内置策略定义（cutoff / DTI / MOB / 定价 margin） | 可复用；但只有一种"世界"：静态回放 |
| 自定义数据 `api/custom.py` + `strategies/contract.py` | CSV 上传 → `DataView` + 逻辑列↔物理列映射 | **强资产**，仿真环境接入外部数据的现成入口 |
| 策略执行 `strategies/sandbox.py` / `runner.py` | 子进程 + rlimit + 禁网 + import 白名单，契约为 `STRATEGY_META / score() / approve()` | **强资产**；但威胁模型是"可信但粗心的用户"，LLM 写代码后需升级 |
| 指标层 `services/metrics.py` + fixtures | L1 模型质量 / L2 商业价值 / L3 风险 / L4 Swap-set / L5 公平性，含 KS、AUC、Brier、PSI/CSI、Vintage、Roll rate、DI ratio、置换重要性 | **最强资产**，直接就是 Agent 的评估函数 |
| 持久化 `db/` | SQLite：`custom_strategies` / `custom_datasets` / `column_mappings` / `runs(config,result,snapshot_sha)` | 够用，但 `runs` 只是结果堆，不是实验注册表 |
| AI 层 `services/llm.py` + `api/ai.py` | DeepSeek SSE 五个端点：parse-config / analyze-layer / chat / report / compare | **只读解说员**：不能调用工具、不能发起实验、不能验证自己 |
| 前端 | React 18 + Chart.js，Config → Execution → Results(L1–L5) → History，中英双语 | 面向"一次实验"设计，无实验树 / 无 diff / 无 Agent 会话 |

---

## 2. 差距分析：五个致命缺口

### 缺口 1 — 实验没有身份（Identity）
`snapshot_sha = sha256(champion|challenger|beta|sample)`。**没有覆盖** seed、策略代码、数据集内容、参数、指标版本。
→ 两个数值不同的实验可以拥有同一个 id。Agent 一旦开始批量生产实验并引用 run_id 作为证据，结论就不可审计。

### 缺口 2 — 实验会被覆盖（Immutability）
`POST /{run_id}/reslice` 用 `INSERT OR REPLACE` **原地覆盖**原 run。
→ 证据链被销毁：昨天引用的 run_id，今天指向另一份数据。这是 agentic 场景下最严重的一个 bug 级设计。

### 缺口 3 — 策略不可参数化（Controllability）
`ExperimentConfig` 只能选"哪三个策略"，不能调"策略的任何一个旋钮"；上传策略的 `params` 只取 `STRATEGY_META` 默认值，无法覆盖；`seed` 写死 42。
→ Agent 无法做参数搜索，只能换策略名，实验空间接近于零。

### 缺口 4 — 运行不可观测（Observability）
回测是同步请求，`asyncio.to_thread` 里算完直接返回；没有 run 状态、不能轮询、不能取消、不能批量。
→ Agent 要并发几十次实验时，只能长连接死等。

### 缺口 5 — 没有记忆（Memory）
`runs` 表只有 config 和 result，没有"为什么做这个实验"和"结论是什么"，没有父子关系，没有标签。
→ Agent 每次都从零开始，重复实验无法命中缓存，平台不沉淀资产。

**另外两个中期风险**：
- 只有 L1a 重放型环境（历史标签直接可见）。`ri_mode: "parceling"` 在 `ExperimentConfig` 里定义了但**全代码未使用**——拒绝推断是空的，长期结论不可信。
- 沙箱是 demo 级。当写策略的是 LLM 而不是人，需要真隔离（容器 / nsjail / seccomp）。

---

## 3. 目标架构（六层）

```
L5  体验层        实验树 / 多 run diff / Agent 会话 / 报告
                 （现有 React 前端 + 新增实验树与对比视图）
─────────────────────────────────────────────────────────
L4  Agent 层      Hypothesis · Designer · Executor · Analyst · Critic
                 工具面 = MCP / tool schema（见 §4.3）
─────────────────────────────────────────────────────────
L3  治理与评估    指标契约（L1–L5 冻结口径）· Guardrail（禁用字段 / DI 阈值 /
                 敞口上限）· 预算（实验数 / 算力 / token）· 人工审批闸门
─────────────────────────────────────────────────────────
L2  实验注册表    Run（不可变）· Manifest（复现哈希）· Lineage（父子）·
                 Hypothesis/Conclusion/Tags · 缓存命中
─────────────────────────────────────────────────────────
L1  执行内核      Job 生命周期（queued→running→succeeded/failed/cancelled）
                 策略沙箱 · 确定性执行（seed + 版本 + 参数）
─────────────────────────────────────────────────────────
L0  仿真环境      L0a 重放（现有） → L0b 反事实（拒绝推断） → L0c 行为
                 （接受率 / 用信弹性 / 迁移矩阵 / 多期滚动 / 蒙特卡洛）
```

三个一等公民对象：

| 对象 | 定义 | 落地位置 |
|---|---|---|
| **Experiment Run** | 不可变记录 = manifest + 结果 + 血缘 + 结论 | `runs` 表扩列 + `core/manifest.py` |
| **Environment** | 数据 + 世界假设（回放 / 反事实 / 行为），带版本与置信度 | P3 新增 `app/envs/` |
| **Policy** | 可版本化、可 diff、可程序生成的策略 artifact（已有契约） | `strategies/contract.py`（已具备） |

---

## 4. 接口契约

### 4.1 Run Manifest（复现契约）— 已实现

`app/core/manifest.py`。把**一切会改变数值的输入**折叠成规范化 JSON，取 SHA-256：

```jsonc
{
  "manifest_sha": "…64 hex…",
  "body": {
    "engine_version": "1.1.0",
    "metric_version": "l1-l5/2026.09",
    "dataset":  { "kind": "synthetic", "sample_id": "…", "n_rows": 80000,
                  "seed": 42, "generator": "synthetic/1.0", "sha": "…" },
    "strategies": {
      "champion":   { "kind": "builtin", "id": "v2.2", "definition_sha": "…" },
      "challenger": { "kind": "custom",  "id": "…",    "code_sha": "…",
                      "overrides": { "target_approval_rate": 0.55 } }
    },
    "seed": 42,
    "slice": { "dim": null, "value": null },
    "windows": { "lookback_months": 6, "perf_window_months": 12 },
    "ri_mode": "parceling"
  },
  "lineage":    { "parent_run_id": null, "root_run_id": "…" },
  "created_by": "agent:designer"
}
```

不变式：**相同 `manifest_sha` ⇒ 相同数值；数值不同 ⇒ `manifest_sha` 必不同。**
自定义数据集按**文件内容**哈希，内置数据集按**生成器输入**哈希——换了数据换了 id，改了策略定义也换 id。

### 4.2 API（P1 已交付）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/experiments/run` | 同步回测（前端交互路径，保持兼容） |
| POST | `/api/experiments/submit` | **异步提交**，202 返回 `run_id` + `manifest_sha` + `identical_prior_runs`（缓存提示） |
| GET | `/api/experiments/jobs` | 生命周期列表（可按状态过滤） |
| GET | `/api/experiments/{id}/status` | 轮询状态：queued / running / succeeded / failed / cancelled |
| POST | `/api/experiments/{id}/cancel` | 取消在跑的实验 |
| POST | `/api/experiments/{id}/reslice` | **产生新 run**，血缘指向父 run（不再覆盖） |
| GET | `/api/experiments/{id}/manifest` | 复现文档 |
| GET | `/api/experiments/{id}/lineage` | 同一 root 的全部实验（一条实验线索） |
| POST | `/api/experiments/{id}/annotate` | 写入 hypothesis / conclusion / tags |

`ExperimentConfig` 新增（全部可选、向后兼容）：

```jsonc
{
  "seed": 42,
  "policy_overrides": { "v2.3": { "target_approval_rate": 0.55, "dti_limit": 0.70 } },
  "param_overrides":  { "custom:abc123": { "cutoff": 0.08 } }
}
```

内置策略可调旋钮白名单（`fixtures._OVERRIDABLE_POLICY`）：
`target_approval_rate` · `dti_limit` · `mob_months` · `mob_dpd_max` · `score_cutoff` · `limit_increase_min/max`。
白名单之外一律报错——Agent 能移动阈值，但**不能重新定义策略**。

### 4.3 Agent 工具面（P2 已实现）

已实现为 `app/agent/tools.py` 的注册表，通过 `GET /api/agent/tools` 自描述、`POST /api/agent/tools/{name}` 调用。每个工具都是确定性薄封装，业务逻辑仍在服务层；同一份 schema 后续可直接包成 MCP server（P2b）。

| 工具 | 签名要点 | 说明 |
|---|---|---|
| `list_strategies` / `list_datasets` | — | 发现可用素材 |
| `submit_experiment` | `config, hypothesis, created_by` → `run_id` | 唯一的"花钱"入口，受预算约束 |
| `get_run_status` / `wait_for_runs` | `run_id[]` | 批量等待 |
| `get_metrics` | `run_id, layer, strategy?` | 只回 KPI，不回全量曲线（省 token） |
| `compare_runs` | `run_id[], metric[]` | 多 run 对齐成表 |
| `sensitivity_scan` | `base_config, knob, values[]` | 一次生成一组 run（服务端展开，避免 Agent 逐个调用） |
| `search_experiments` | `tags/hypothesis/manifest_sha` | **先查再跑**，命中即复用 |
| `annotate_run` | `run_id, conclusion, tags` | 沉淀记忆 |
| `check_guardrails` | `run_id` | 返回违规项（DI < 0.8、禁用字段、敞口超限） |

Agent 角色分工：**Hypothesis**（从指标异动/目标提假设）→ **Designer**（翻译成实验配置，含对照与停止条件）→ **Executor**（调度重试）→ **Analyst**（读结果做归因）→ **Critic**（对抗校验：穿越、样本偏差、多重比较、过拟合、结论超出环境能力档位）。
搜索策略：LLM 负责**提假设 + 缩空间**，贝叶斯优化/网格负责**搜参数**——不要让 LLM 盲搜参数空间。

### 4.4 治理契约（P2 已实现）

- **指标口径冻结**：`METRIC_VERSION` 进 manifest，Agent 不得自造指标口径。
- **Guardrail**：禁用字段清单（性别等不得入模）、DI ratio 阈值、敞口上限；违规 run 标红且不得进入"候选策略"。
- **人审闸门**：Agent 最远推进到"候选策略 + 实验报告"，上线永远是人的动作。
- **预算**：每个 Agent 会话限制实验次数 / 算力 / token，Designer 层先做实验去重（查 `manifest_sha`）。

---

## 5. 分阶段路线

| 阶段 | 交付物 | Agent 自主度 | 状态 |
|---|---|---|---|
| **P1 地基** | Manifest 复现哈希 · Run 不可变 + 血缘 · policy/param/seed 可调 · 异步 Job 生命周期 · 实验注册表列（hypothesis/conclusion/tags）+ 缓存查询 | 只读 | ✅ 本分支已交付 |
| **P2 Agent 闭环** | 工具面 · Designer/Executor/Analyst/Critic 编排 · Guardrail + 预算 · `sensitivity_scan` 批量展开 | 提案权 | ✅ 后端内核已交付（MCP server 与前端实验树留待 P2b） |
| **P3 仿真环境** | `app/envs/`：环境注册表（能力/不能力声明）· 拒绝推断四种方法 + **方法误差标定** · 多种子复现与排序稳健性 | 提案权 | ✅ L0b 已交付（L0c 行为仿真未建） |
| **P4 在线校准** | 影子流量 / AB 结果回灌校准仿真环境 · 环境置信度指标 · 策略上线审批流 | 建议 + 人审上线 | 待评估 |

**P1 之后立刻能做到的事**（今天做不到的）：
1. 对同一策略跑 `target_approval_rate ∈ {0.30…0.70}` 的扫描，每个点都是独立可引用的 run；
2. 同一配置换 5 个 seed 跑，看结论是否稳健（而不是过度解读一次抽样）；
3. 任意 run 都能回答"你是怎么算出来的"——manifest 一取即知；
4. 重复实验先命中 `identical_prior_runs`，不再重复烧算力。

---

## 5.1 P2 交付清单（本分支）

**新增**
- `app/core/runs.py` — 运行执行服务从路由层剥离。HTTP 与 Agent 走同一条路径，
  谁都不能产出对方产不出的 run（同 manifest、同血缘、同落库）。
- `app/agent/tools.py` — 9 个确定性工具的注册表 + JSON Schema 自描述：
  `list_strategies` `list_datasets` `submit_experiment` `sensitivity_scan`
  `get_metrics` `compare_runs` `get_run_status` `search_experiments`
  `annotate_run` `check_guardrails`。花算力的工具被显式标记 `spends_compute`。
- `app/agent/guardrails.py` — 确定性红线：DI 四分之五规则（阻断）、核准户数下限（阻断）、
  受保护属性入模（阻断）、swap-set p 值不显著（警告）、坏账上限、AUC 下限、
  极端 override（警告）。**缺失指标不等于零指标**，无数据的策略跳过而非误报。
- `app/agent/budget.py` — 会话预算（实验数 / LLM 调用数 / 墙钟），在工具层强制，
  不在 prompt 里劝说。命中缓存不计费。
- `app/agent/orchestrator.py` — Designer → Executor → Analyst → Critic。
  Critic 拿到 guardrail 报告作为**不可推翻的事实**：只要存在阻断项，
  verdict 强制降为 `not_supported`，置信度封顶 0.3。
- `app/api/agent.py` — 工具端点、会话端点、`/investigate` 与 `/investigate/stream`（SSE）。

**关键设计点**
- **紧凑指标**：`_compact()` 把一次 run 的约 200 KB 图表数据压成决策相关的十几个数。
  喂全量图表给模型既贵又会诱发编造精度。
- **先查后跑**：`search_experiments` + manifest 缓存命中，重复实验不重复烧算力。
- **无 key 可跑**：Designer/Analyst/Critic 三步都有确定性兜底，没有 API key 时
  整个闭环仍然跑通（默认计划 = 基线 + 通过率扫描），测试因此可离线运行。
- **兜底 Critic 永远说出环境边界**：当前只有历史回放，任何长期客群推断都不成立。

**测试**：172 passed（P1 后 143 + 新增 29）。

## 5.2 P3 交付清单（本分支）

### 核心思路：不是"能不能估"，是"估得有多离谱"

这份合成账簿所有人都有真实标签，直接做拒绝推断没有意义。所以环境层反过来用：
**先按真实世界的样子遮蔽冠军拒绝客群的标签，再用各种 RI 方法估回来，最后拿被遮蔽的真值算方法误差。**

每家信贷机构都在做第 2 步并把结果当测量值汇报，几乎没人报第 3 步。本平台每个 run 自带误差条。

实测（consumer_2024q1q2，冠军 v2.2 通过率 23%）：

| 方法 | v2.3 swap-in 估计坏账 | 真实坏账 | 偏差 | 相对误差 |
|---|---|---|---|---|
| none（忽略拒绝客群） | 0.00% | 2.24% | −2.24pp | 100%（结构性低估） |
| parceling（×2 惩罚） | 4.10% | 2.24% | +1.86pp | **83%** |
| fuzzy / augmentation | 见 `compare_ri_modes` | — | — | — |

行业惯用的 parceling 惩罚因子在这份账簿上**高估了 83%**——这正是 guardrail 现在会拦截的情况。

**新增**
- `app/envs/base.py` — 环境注册表。每个环境必须声明 `valid_for` 与 **`not_valid_for`**，
  以及置信度档位；这两个字段随 run 一起返回，结论的适用边界不再靠人记。
- `app/envs/reject_inference.py` — 四种方法（none / parceling / fuzzy / augmentation）
  + `report()` 误差标定 + `compare_modes()` 横比。`ri_mode` 这个从 v1.0 起
  定义了却全代码未使用的字段，到这里才真正落地。
- `app/envs/replication.py` — 多种子复现：mean/std/CI95，以及**排序是否翻转**。
  排序翻转 = 该差异来自抽样，不是策略差异。
- 工具层新增 `list_environments` / `replicate_across_seeds` / `compare_ri_modes`。

**Guardrail 新增两条**
- `replay_only_environment`（警告）：回放环境下的任何"放开准入后客群变化"推断都不成立。
- `reject_inference_unreliable`（**阻断**）：RI 方法相对误差 > 50% 时，
  swap-in 风险结论直接不可用——方法误差比它声称的效应还大。

**Agent 闭环新增一步**
findings 之后、critique 之前插入多种子复现：Agent 花掉剩余预算去回答
"这是策略差异还是抽样差异"。**排序翻转会确定性地把 verdict 降为 `not_supported`、
置信度封顶 0.25**，与 guardrail 阻断项同等级别，模型说服不了。

**测试**：196 passed（P2 后 172 + 新增 24）。

## 6. 风险与边界

| 风险 | 说明 | 对策 |
|---|---|---|
| **闭环偏差** | 策略变了客群就变；L0a/L0b 都没有行为反馈 | 环境层已强制声明 `not_valid_for` 且 guardrail 会警告；L0c 行为仿真建成前，不用于额度政策长期决策 |
| **沙箱强度** | 写策略的从人变成 LLM，现有 demo 级隔离不够 | P2 同步升级为容器/nsjail + 只读文件系统 + 资源配额 |
| **成本失控** | Agent 实验数指数级增长 | manifest 缓存 + 会话预算 + Designer 去重（三者缺一不可） |
| **多重比较** | 跑 200 个实验必然出现"显著" | Critic 强制校正（Bonferroni/FDR），结论必须带样本量与 p 值 |
| **过度分层** | L0c 行为仿真一上来就做，投入产出比最差 | 先 L0a + 注册表 + Critic 跑通，再谈行为仿真 |

---

## 7. 本分支交付清单（P1）

**新增**
- `app/core/manifest.py` — 复现哈希、数据集/策略指纹、manifest 构建
- `app/core/jobs.py` — run 生命周期注册表（queued/running/succeeded/failed/cancelled）
- `tests/test_agentic_p1.py` — 21 个用例，覆盖身份 / 可控性 / 生命周期 / 记忆

**修改**
- `app/data/fixtures.py` — 策略旋钮白名单 `_merged_policy()`，`_eligible_mask/_pd_threshold/_approve_mask/_compute_l2/l4/l5` 全链路支持 overrides（默认 None ⇒ 行为逐字节不变）
- `app/services/metrics.py` — `seed` / `policy_overrides` / `param_overrides` 贯通两条回测路径；`snapshot_sha` 纳入 seed 与切片
- `app/models/schemas.py` — `ExperimentConfig` 新增 seed / policy_overrides / param_overrides；新增 `RunSubmit`、`RunAnnotation`
- `app/api/experiments.py` — `_execute_run()` 统一落库路径；reslice 改为派生新 run；新增 submit / jobs / status / cancel / manifest / lineage / annotate
- `app/db/engine.py` — `runs` 表幂等迁移（新增 9 列 + 3 个索引）
- `app/db/repository.py` — 扩展 `create_run`，新增 `annotate_run` / `find_runs_by_manifest` / `get_lineage` / `update_run_status`
- `app/strategies/builtin_adapter.py` — 透传 overrides
- `tests/test_api.py` — reslice 用例改为验证不可变语义与血缘

**测试**：143 passed（原 121 + 新增 22）。前端无需改动：`ResultsScreen` 已用返回体整体替换结果，新 `run_id` 自动生效。

**破坏性变更（仅一处）**：`POST /{run_id}/reslice` 返回的 `run_id` 与请求中的不同（派生新 run）。这是本次升级的核心目的。
