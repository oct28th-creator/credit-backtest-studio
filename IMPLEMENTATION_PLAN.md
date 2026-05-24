# 信贷回测工作室 (Credit Backtest Studio) 技术实施与测试保障计划

本项目目前存在若干安全、逻辑计算和性能缺陷，尤其是新发现的**重新切片 (Reslice) 后端接口缺失**，以及直方图百分比分母使用 `vals.sum()` 导致的**数据失真 Bug**。

作为**测试工程师**，我编写了本实施与测试保障计划。我们将在修复前先明确修改内容、测试手段以及期望的测试输出。

---

## 一、 用户审批项

> [!IMPORTANT]
> **1. Reslice 接口路由规范决策**
> - **现状**：前端通过 API 客户端请求 `/api/run/{run_id}/reslice`，但后端路由挂载在 `/api/experiments/` 下，且无 reslice 端点。
> - **方案 A (推荐)**：修改前端 [client.ts](file:///Users/lin/Documents/Qoder/credit-backtest-studio/frontend/src/api/client.ts) 中的路径为 `/experiments/{run_id}/reslice`，保持与后端 experiments 路由的一致性，并在后端 `experiments.py` 中挂载该子路由。
> - **方案 B**：后端在 [main.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/main.py) 中新开一个以 `/api/run` 为前缀的路由，以适配前端现有请求路径。

> [!IMPORTANT]
> **2. 指标硬编码覆盖 (fixtures.py) 的重构策略**
> - **现状**：L1-L3 层计算指标在返回前被硬编码 `targets` 直接改写，破坏了测试和切片过滤的真实性。
> - **建议方案**：
>   - 在后端重构时，默认输出**真实计算指标**（真正调用 NumPy/sklearn/scipy 得到的数值）。
>   - 在 `fixtures.py` 中保留 `targets` 作为“商业修正/拒绝推断参考值”。
>   - 接口中支持可选查询参数 `raw=true/false`，允许前端或测试用例获取原始计算值。

---

## 二、 待解决的问题 (Open Questions)

> [!WARNING]
> **1. 自动化测试执行环境配置**
> 在初步探查中，系统默认的 `python3` 缺少 `pytest` 等测试框架库。
> - **提议**：实施方案执行前，需在 `backend/` 下配置虚拟环境 `venv` 并安装依赖：
>   ```bash
>   python3 -m venv venv
>   source venv/bin/activate
>   pip install -r requirements.txt pytest
>   ```
> - **确认**：是否允许我们在执行计划时创建该 `venv` 虚拟环境以保证测试套件可运行？

---

## 三、 拟议变更与测试方案

我们以模块和 Bug 优先级为维度，详细定义修改内容和对应的测试用例。

### 1. 部署脚本与路径修复 (P0)
#### [MODIFY] [server-setup.sh](file:///Users/lin/Documents/Qoder/credit-backtest-studio/deploy/server-setup.sh)
- **修改内容**：
  将脚本中所有 `/var/www/credit-backtest-studio/app/...` 路径前缀修改为真实存在的 `/var/www/credit-backtest-studio/...`。
- **QA 测试方案**：
  - **静态测试**：通过 Shell 语法检查和路径存在性静态核验。
  - **集成测试**：在测试环境中模拟执行该脚本的关键路径，确保在根目录下能正确找到 `backend/requirements.txt` 和 `deploy/nginx.conf`。

### 2. API Key 部分泄露修复 (P0)
#### [MODIFY] [ai.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/ai.py)
- **修改内容**：
  移除 `/api/ai/status` 响应体中的 `api_key_hint` 属性，仅保留 `api_key_present: bool`。
- **QA 测试方案**：
  - 在 [test_api.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/tests/test_api.py) 中新增测试类 `TestAIStatusSecurity`。
  - 发送 `GET /api/ai/status` 请求，断言响应 JSON 中 **不包含** `api_key_hint` 键值。

### 3. 重新切片 (Reslice) 功能闭环 (P0)
#### [MODIFY] [client.ts](file:///Users/lin/Documents/Qoder/credit-backtest-studio/frontend/src/api/client.ts) & [experiments.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/experiments.py)
- **修改内容**：
  - **前端**：将 `API.reslice` 请求路径更新为 `/experiments/{run_id}/reslice`。
  - **后端**：在 `experiments.py` 中添加端点 `@router.post("/{run_id}/reslice")`。
  - **处理逻辑**：
    1. 从内存 `_RUN_STORE` 中获取原 `run_id` 的实验配置。
    2. 使用原配置中的参数从缓存或生成器中提取样本数据。
    3. 解析请求中的 `SliceRequest` (`slice_dim` 和 `slice_value`)。
    4. 对数据调用 `_apply_slice` 过滤。
    5. 重新进行 L1-L5 层级的指标计算（重算通过率、坏账、KS等）。
    6. 更新 `_RUN_STORE[run_id]` 并返回更新后的 `RunResult`。
- **QA 测试方案**：
  - **集成测试**：在 `test_api.py` 中新增 `TestResliceEndpoint`：
    - 步骤 1：调用 `POST /api/experiments/run` 创建一个回测，获取 `run_id` 和初始样本大小（如 50,000）。
    - 步骤 2：对该 `run_id` 调用 `POST /api/experiments/{run_id}/reslice` 传递切片参数（如 `{"slice_dim": "gender", "slice_value": "female"}`）。
    - 步骤 3：验证返回响应为 200，且 `sample_size` 明显减小（如女客户占 ~42%，大小应接近 21,000），且 `layers` 中的 KPI 发生变化。
    - 步骤 4：验证原 `_RUN_STORE` 已同步更新。

### 4. 信用分直方图分箱百分比 Bug 修复 (P1)
#### [MODIFY] [stability.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/services/stability.py)
- **修改内容**：
  将分箱比例计算公式第 152 行的分母 `vals.sum()` 修正为 `len(vals)`。
  ```python
  # 修改前
  "pct": round(float(counts[i] / (vals.sum() + 1e-8)), 4)
  # 修改后
  "pct": round(float(counts[i] / (len(vals) + 1e-8)), 4)
  ```
- **QA 测试方案**：
  - **单元测试**：在 `test_metrics.py` 中新增直方图比例测试。
  - 构造包含特定数值的 `vals` 数组（例如 `[600, 600, 600, 600]`，共 4 个样本，总和为 2400）。
  - 调用 `compute_score_distribution`，断言每个箱体中的 `pct` 比例总和为 `1.0`（而不是近乎零的 `counts[i]/2400`）。

### 5. 密集计算阻塞事件循环修复 (P1)
#### [MODIFY] [experiments.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/api/experiments.py)
- **修改内容**：
  将 `/experiments/run` 接口中的同步 `run_backtest` 调用，包装在 `asyncio.to_thread` 中运行：
  ```python
  raw = await asyncio.to_thread(
      run_backtest,
      champion_id=config.champion,
      ...
  )
  ```
- **QA 测试方案**：
  - **并发性能测试**：使用 Python 异步测试脚本（或 pytest-asyncio）并发发起两个回测请求。
  - 期望表现：如果成功切换为多线程运行，这两个大消耗回测应当**并发执行，耗时不会翻倍**；在此期间，健康检查接口 `/api/health` 应当能即时返回，不出现挂起或无响应。

### 6. 数据缓存限制与内存防护 (P2)
#### [MODIFY] [metrics.py](file:///Users/lin/Documents/Qoder/credit-backtest-studio/backend/app/services/metrics.py)
- **修改内容**：
  引入 LRU 缓存淘汰机制（使用 `functools.lru_cache` 或者是固定大小控制），当缓存的生成数据集超过 5 个时自动驱逐老的数据集。
- **QA 测试方案**：
  - **单元测试**：编写缓存迭代测试，循环调用 `get_sample_data` 传递 10 个不同的 seed。
  - 检查内存使用和 `_DATA_CACHE` 长度，验证其键值对总数不超过预设上限（如 5），避免内存泄漏。

---

## 四、 自动化与手工验证流程

### 1. 自动化测试套件执行 (QA 标准)
修改完成后，将依次运行以下测试：
1. **测试准备**：
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt pytest
   ```
2. **运行单元与集成测试**：
   ```bash
   pytest -v tests/
   ```
3. **输出期望**：测试用例数应从 39+ 增加至 45+，所有测试用例必须通过（100% Pass）。

### 2. 手工 UI 验证
1. **部署切片验证**：
   - 打开平台前端页面。
   - 运行一次默认配置回测。
   - 进入 `L2 Panel` 或直方图组件，使用底部的 `Slice Filter` 切换切片（例如切换为 `Gender = Female`）。
   - **检查要点**：通过 Chrome 开发者工具监控网络，确保 `/api/experiments/{run_id}/reslice` 返回 200，且前端页面所有图表和指标卡实时更新（数值区别于 Mock 数据）。
2. **直方图占比验证**：
   - 检查 approved 信用分直方图，验证各柱子高度百分比之和为 100%（例如 0.25, 0.40...），而不是先前的微小百分比数值。
