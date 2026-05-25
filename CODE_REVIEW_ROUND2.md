# 二次代码 Review 报告

**项目**: credit-backtest-studio  
**Review 范围**: 修复提交 `8b775af` 之后的完整代码库  
**Review 日期**: 2026-05-25  
**Review 方法**: 全量代码走查，覆盖 backend（Python/FastAPI）、frontend（React/TypeScript/Vite）、deploy（nginx/systemd/CI）

---

## 1. 背景

首次 Review（`CODE_REVIEW_REPORT.md`）识别 27 个问题，分 4 个严重级别。修复提交 `8b775af` 解决了核心问题：

| 已修复 | 说明 |
|--------|------|
| 移除硬编码指标覆盖 | L1-L3 全面改为从合成数据计算，指标真实响应 slicing |
| 添加 `/reslice` 端点 | 维度切片回测功能，含完整测试 |
| 修复 AI `/status` 密钥泄露 | 移除 `api_key_hint`，只保留布尔标志 |
| LRU 数据缓存 | `OrderedDict` + max=8，防止无界增长 |
| `asyncio.to_thread` | CPU 密集型操作不再阻塞事件循环 |
| 评分分布 `pct` 计算修复 | 由 `count/sum(scores)` 改为 `count/N` |
| 策略 DSL 落地（months_clean 字段） | MOB 零逾期规则通过真实数据生效 |
| v2.4-Beta 差异性影响成因修正 | 由"无理由"→行为模型薄文件门控 |
| 分页逻辑参数约束 | offset/limit 添加 `ge`/`le` 校验 |
| CORS 配置 | 从环境变量读取，不再硬编码 |

本次 Review 聚焦 **修复后的剩余问题** 和 **修复引入的新问题**。

---

## 2. 发现清单

### 2.1 P1 — Bug / 不一致性

#### P1-1: `fairness.py` 残留 DI 硬编码覆盖

**文件**: `backend/app/services/fairness.py:65-67`

```python
# v2.4-Beta compliance override for young customers
if strategy_id == "v2.4-Beta" and key == "young_vs_core":
    di_ratio = 0.77
```

**问题**: 上一次修复已从 `fixtures.py:_compute_l5` 中移除了此硬编码，改为从合成数据计算。但 `fairness.py` 中的 `compute_fairness_report()` 函数**仍保留硬编码覆盖**。

**影响**: 调用 `compute_fairness_report()` 与 `apply_strategy()` 会得到不同的 DI 值。虽然当前主流路径走 `fixtures.py`，但 `fairness.py` 是公开 API，任何未来调用方都会读到不一致的结果。同时破坏"数据驱动"修复的设计原则。

**修复建议**: 移除 `fairness.py:65-67` 整段。

---

#### P1-2: `stability.py` 使用 `hash()` 导致非确定性

**文件**: `backend/app/services/stability.py:64`

```python
drift_seed = int(seed + m * 997 + hash(strategy_id) % 10000)
```

**问题**: Python 的 `hash()` 自 3.3 起默认开启随机化（`PYTHONHASHSEED` 环境变量）。跨进程运行时 `hash(strategy_id)` 产生不同结果，导致：

- CI 中 `pytest` 与本机结果不一致
- 同一 `seed` 参数在不同进程中得到不同的月度偏移

**对比**: 代码库其他所有确定性哈希均使用 `hashlib.md5()`（如 `fixtures.py:394`、`stability.py:53`）。

**修复建议**:
```python
import hashlib
drift_seed = int(hashlib.md5(f"{strategy_id}_{seed}_{m}".encode()).hexdigest(), 16) % (2**32)
```

---

### 2.2 P2 — 架构 / 健壮性

#### P2-1: `_RUN_STORE` 跨模块紧耦合，缺少并发保护

**文件**:
- `backend/app/api/experiments.py:20` - 定义
- `backend/app/api/ai.py:15` - import
- `backend/app/api/reports.py:9` - import

```python
# experiments.py
_RUN_STORE: dict[str, dict] = {}

# ai.py
from app.api.experiments import _RUN_STORE

# reports.py
from app.api.experiments import _RUN_STORE
```

**问题**:

1. **紧耦合**: `ai.py` 和 `reports.py` 依赖 `experiments.py` 的模块级私有变量 `_RUN_STORE`。任何重命名或存储方案变更都牵涉 3 个模块。
2. **无并发保护**: 虽然 uvicorn 使用单 worker（`--workers 1`），但 `asyncio.to_thread` 释放 GIL 期间，多个并发的 `/run` 请求可能在时间线上交错写入同一个 `run_id`（理论上 `uuid4()[:12]` 碰撞概率极低，但 lock-free 模式不够明确）。
3. **无生命周期管理**: dict 无限增长，没有 TTL 或数量上限。长期运行的服务器会 OOM。

**修复建议**: 抽取 `RunStore` 类，提供 `get/put/list` 接口，并添加 `asyncio.Lock` 保护写入。

---

#### P2-2: `list_experiments` 全量内存拷贝，分页参数未物尽其用

**文件**: `backend/app/api/experiments.py:382-398`

```python
runs = list(reversed(list(_RUN_STORE.values())))
return {
    "runs": [
        { ... }
        for r in runs[offset: offset + limit]
    ],
}
```

**问题**: `list(reversed(list(...)))` 创建了两次完整列表拷贝（一次 `list(_RUN_STORE.values())`，一次 `reversed(list(...))` 再 `list()`）。对于 10K+ 条记录的场景，每次列表请求都分配 ~800KB+ 内存。

**影响**: 当前 MVP 规模下无实际性能问题，但分页设计本意是避免全量加载，当前实现让 `offset`/`limit` 形同虚设。

**建议**: 如果已决定远期接入数据库，加 `# TODO: replace with DB cursor-based pagination` 注释即可。

---

#### P2-3: `swap_set.py` 与 `fixtures.py` 存在代码重复和维护分裂

**文件**:
- `backend/app/services/swap_set.py` — `compute_swap_set()`, `compute_three_way_swap()`
- `backend/app/data/fixtures.py:586` — `_compute_l4()`

**问题**: 两个模块都实现了 4 象限 swap-set 矩阵 + score band 一致性分析。`swap_set.py` 额外有 channel breakdown 和 incremental value 计算，但**似乎不被主流调用**（`run_backtest` → `_compute_l4` 路径直接使用 `fixtures.py`）。

**风险**: 两份几乎相同的逻辑，未来改良一处可能遗漏另一处，产生数据分歧。

**建议**: 确认 `swap_set.py` 是否被外部调用。如未被使用，归档或删除；如仍需要，让 `_compute_l4` 委托给 `swap_set.py` 而非重复实现。

---

### 2.3 P3 — 代码质量

#### P3-1: LLM JSON 解析逻辑重复 3 次

**文件**: `backend/app/services/llm.py`

| 位置 | 函数 |
|------|------|
| :405–410 | `stream_parse_config` |
| :492–496 | `stream_analyze_layer` |
| :653–657 | `stream_compare_strategies` |

三处均包含相同的代码块：
```python
json_str = answer_buf
if "```json" in json_str:
    json_str = json_str.split("```json")[1].split("```")[0].strip()
elif "```" in json_str:
    json_str = json_str.split("```")[1].split("```")[0].strip()
result = json.loads(json_str)
```

**建议**: 提取为 `_extract_json(response: str) -> dict` 私有函数。

---

#### P3-2: `language` 参数缺少枚举校验

**文件**: 多处 API 端点

```python
language: str = Query(default="zh", description="Language: zh or en")
```

传入 `language=fr` 时不会报错，LLM system prompt 会走中文分支。虽然有 `settings.cors_list` 等已验证的校验模式，但 language 参数缺少显式约束。

**建议**: 使用 Pydantic `Literal["zh", "en"]` 或 `Query(pattern=r"^(zh|en)$")`。

---

#### P3-3: `run_id` 截断未注释

**文件**: `backend/app/api/experiments.py:350`

```python
run_id = str(uuid.uuid4())[:12]
```

**问题**: UUID4 前 12 位 hex 字符提供 48-bit 熵，1M 次运行下碰撞概率 `≈ 0`。但截断操作降低了信息量，且无注释说明为何截断。

**建议**: 添加注释 `# 12-char prefix is enough for MVP; full UUID if we scale`。

---

#### P3-4: `RunResult.layers` 类型为裸 `dict`

**文件**: `backend/app/models/schemas.py:27`

```python
class RunResult(BaseModel):
    layers: dict  # L1-L5 computed results
```

**问题**: 类型检查器（mypy/pyright）无法为嵌套的 L1-L5 结构提供任何提示。注释 `# L1-L5 computed results` 对人和工具都不够具体。

**建议**: 至少定义 `TypedDict` 描述顶层结构：
```python
class LayerResult(TypedDict, total=False):
    l1: dict
    l2: dict
    l3: dict
    l4: dict
    l5: dict
```

---

### 2.4 P4 — 低优先级 / 建议

#### P4-1: 部署脚本使用 `--break-system-packages` 不够稳定

**文件**: `.github/workflows/deploy.yml:84-85`

```bash
pip3 install -r requirements.txt -q --break-system-packages
```

PEP 668 设计初衷是保护系统 Python 不被破坏。`--break-system-packages` 是破坏性绕过，可能在 OS 升级 pip 版本后失效。

**建议**: 在 `server-setup.sh` 中创建 venv，deploy workflow 中通过 venv 安装：
```bash
python3 -m venv /opt/backtest-studio/venv
/opt/backtest-studio/venv/bin/pip install -r requirements.txt
```

---

#### P4-2: Mock 数据日期硬编码

**文件**: `frontend/src/api/client.ts:165-168`

```typescript
const MOCK_HISTORY: RunHistoryItem[] = [
  { run_id: 'run-20241101-001', timestamp: '2024-11-01T10:22:00Z', ... },
  ...
];
```

**问题**: 硬编码的 2024-11 日期会逐渐与当前时间差距越来越大。

**建议**: 运行时生成相对日期（`new Date(Date.now() - ...)`），或至少加注释说明。

---

#### P4-3: SSE 事件解析对非标准格式容忍度低

**文件**: `frontend/src/api/client.ts:62-64,84`

```typescript
const events = buf.split('\n\n');
buf = events.pop() ?? '';
```

**问题**:
1. SSE 协议允许多行 `data:` 字段，也允许以 `:` 开头的注释行。当前实现按 `\n\n` 分割后取所有 `data:` 行，忽略了注释行和 `event:` 字段。
2. `[DONE]` 检查（line 64）是多余的——后端只发送 `event: done\ndata: {}\n\n`。
3. 半包场景（`data:` 跨 chunk 边界）未处理，虽然在高速网络下极少发生。

**建议**: 当前实现对已知后端输出格式足够。如果未来接入第三方 SSE 源，需重构为协议兼容的解析器。

---

#### P4-4: `_make_shap_weights` 在 `experiments.py` 与 `fixtures.py:_compute_l5` 中重复定义

**文件**:
- `backend/app/api/experiments.py:292`
- `backend/app/data/fixtures.py:716`

两处定义了结构几乎相同的 simulated SHAP feature importance 数据（`fixtures.py` 版本更完整，含 `direction` 字段）。`experiments.py` 版本用于 `_reshape_layers` 中填充 L5 的 `shap`，而 `fixtures.py` 版本用于 `_compute_l5` 的 `feature_importance`。

**建议**: 统一数据源，移除 `experiments.py` 中的重复定义。

---

## 3. 总结

| 严重度 | 数量 | 典型问题 |
|--------|------|----------|
| P1 — Bug | 2 | DI 硬编码残留、hash 非确定性 |
| P2 — 架构 | 3 | _RUN_STORE 耦合、全量拷贝、swap_set 重复 |
| P3 — 质量 | 4 | JSON 解析重复、language 缺校验、run_id 截断、layers 裸类型 |
| P4 — 建议 | 4 | pip 不稳定、mock 日期、SSE 健壮性、SHAP 重复 |

| 状态 | 说明 |
|------|------|
| 首次 Review 已修复 | 10 项核心问题 |
| 本次新发现 | 13 项（含 3 项修复引入的遗留不一致） |
| 建议优先修复 | P1-1（fairness.py DI）、P1-2（stability.py hash） |

---

## 4. 修复验证检查清单

- [ ] `fairness.py:65-67`: 删除 DI ratio hardcode
- [ ] `stability.py:64`: 替换 `hash()` 为 `hashlib.md5()`
- [ ] 运行 `cd backend && python -m pytest tests/ -v` 确认全部通过
- [ ] 运行 `cd frontend && npm run build` 确认无编译错误
- [ ] 测试 `/api/ai/status` 不再泄漏 `api_key_hint`
- [ ] 测试 `/api/experiments/{id}/reslice` 返回正确的子群体指标
- [ ] 验证 v2.4-Beta `young_vs_core` DI 值与 `_compute_l5` 一致

---

*Generated with Qoder*
