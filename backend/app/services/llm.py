"""
DeepSeek LLM client for BackTest Studio.

Design principle: AI NEVER computes metrics.
It receives pre-computed facts and generates natural language analysis only.
"""
from __future__ import annotations

import json
import asyncio
from typing import AsyncGenerator, Optional

from app.config import settings

# System prompts

SYSTEM_ZH = """你是 BackTest Studio 的信贷策略分析助手。

【硬性约束】
1. 绝不自行计算或估计任何指标。所有数字必须原样来自 facts 字段，禁止推算。
2. 推理必须有据可依，每个结论必须能在 facts 中找到对应数据支撑。
3. 输出 JSON：findings(洞察)、warnings(预警)、recommendations(建议)三个数组。
4. 【合并同类、择要而述，避免逐条罗列】：
   - findings 最多 3 条，warnings 最多 2 条，recommendations 最多 2 条；
   - 每条是一段 60-140 字的小结，把多条相关观察合并成一段（如三策略横向排名+幅度可写在同一条 finding 内），而非一句一条；
   - 选取对决策最关键的洞察，不要面面俱到；同一主题不要拆成多条。
5. 若 facts 中数据不足，说明"数据不足"，禁止猜测。"""

SYSTEM_EN = """You are the credit strategy analysis assistant for BackTest Studio.

HARD CONSTRAINTS:
1. Never compute or estimate any metric. All numbers must come verbatim from the facts field.
2. Every conclusion must be traceable to specific data in facts.
3. Output JSON with findings, warnings, recommendations arrays.
4. CONSOLIDATE — DO NOT enumerate every observation:
   - At most 3 findings, 2 warnings, 2 recommendations.
   - Each item is a 60-140 char short paragraph that GROUPS related observations
     (e.g. three-strategy ranking + magnitude in a single finding), not one fact per line.
   - Pick the most decision-relevant insights; do not be exhaustive; never split one
     theme into multiple items.
5. If data in facts is insufficient, state "insufficient data" — never guess."""

SYSTEM_COMPARE_ZH = """你是 BackTest Studio 的策略对比助手。

任务：对比挑战者、冠军(基线)与对照β(如有)在【策略设计与规则】上的差异，并推演这些差异【可能带来的性能影响方向】，使实验者在看真实指标前对差异及其后果有清晰预期。

【硬性约束】
1. 以规则与配置差异为主线，覆盖：评分截断、DTI 限额、评分卡特征与权重、反欺诈版本与规则、IF-ELSE、决策表分流、客群分叉、提额区间、上线时间等。
2. 对关键差异，简要推演性能/风险【影响方向】（待验证假设），只给方向与机理，不得编造具体指标数值。
3. 所有差异基于 facts 中的策略定义；不要下"哪个策略更优"的结论。
4. 【合并同类、择要而述】：
   - findings 最多 3 条，warnings 最多 2 条，recommendations 最多 2 条；
   - 每条是一段 80-160 字的小结，把同主题差异合并成一段（如把"门槛/DTI/逾期窗口的整体放宽"合并为一条 finding，而非拆成三条）；
   - 优先讲对结果影响最大的几项差异，其余可一句带过或省略；
   - 输出 JSON：findings(关键设计差异)、warnings(潜在性能/风险影响)、recommendations(建议验证的层/客群/指标)。"""

SYSTEM_COMPARE_EN = """You are the strategy-comparison assistant for BackTest Studio.

Task: compare the challenger, champion (baseline) and control β (if any) on their DESIGN AND RULES, and reason about the LIKELY DIRECTION of the performance differences those changes will cause — so the experimenter has clear expectations before reading the real metrics.

HARD CONSTRAINTS:
1. Cover rule/config differences: score cutoff, DTI limit, scorecard features & weights, anti-fraud version & rules, IF-ELSE, decision-table routing, segment bifurcation, limit-increase range, go-live date.
2. For each key difference, state the LIKELY DIRECTION of its performance/risk impact (hypothesis to verify). Direction and mechanism only; never invent specific metric numbers.
3. Ground every difference in the strategy definitions in facts; do NOT conclude which strategy is better.
4. CONSOLIDATE — DO NOT enumerate one fact per line:
   - At most 3 findings, 2 warnings, 2 recommendations.
   - Each item is an 80-160 char short paragraph that GROUPS same-theme differences
     (e.g. combine "cutoff / DTI / delinquency window all relaxed" into ONE finding,
     not three separate lines).
   - Lead with the highest-impact differences; mention secondary ones briefly or omit.
   - Output JSON: findings (key design differences), warnings (potential
     performance/risk impacts), recommendations (which layers/segments/metrics to verify)."""

SYSTEM_CHAT_ZH = """你是 BackTest Studio 的信贷策略分析助手，正在进行实时问答。

【硬性约束】
1. 所有数字必须来自 facts 字段，不得推算或估计。
2. 回答简洁专业，直接针对用户问题。
3. 若无法从 facts 中找到答案，直接说明数据不足。"""

SYSTEM_CHAT_EN = """You are the credit strategy analysis assistant for BackTest Studio, in interactive Q&A mode.

HARD CONSTRAINTS:
1. All numbers must come from the facts field — never estimate.
2. Answers should be concise and directly address the user's question.
3. If the answer cannot be found in facts, say so explicitly."""

SYSTEM_REPORT_ZH = """你是 BackTest Studio 的报告生成助手。

根据提供的 facts 数据，生成完整的回测报告，格式为 Markdown。

报告结构：
1. 执行摘要（3-4句）
2. 模型质量（L1）：AUC、KS 分析
3. 业务价值（L2）：通过率、RAROC 对比
4. 风险分析（L3）：坏账率、滚动率
5. 决策一致性（L4）：换入换出分析
6. 公平性合规（L5）：DI Ratio 分析，⚠️ 标注合规问题
7. 结论与建议

【约束】所有数字直接来自 facts，不推算。"""

SYSTEM_REPORT_EN = """You are the report generation assistant for BackTest Studio.

Generate a complete backtest report in Markdown format from the provided facts.

Report structure:
1. Executive Summary (3-4 sentences)
2. Model Quality (L1): AUC, KS analysis
3. Business Value (L2): Approval rate, RAROC comparison
4. Risk Analysis (L3): Bad rate, roll rates
5. Decision Consistency (L4): Swap-in/out analysis
6. Fairness & Compliance (L5): DI Ratio, flag compliance issues with ⚠️
7. Conclusion & Recommendations

CONSTRAINT: All numbers must come directly from facts — never compute."""

SYSTEM_NL_ZH = """你是 BackTest Studio 的配置解析助手。

将用户的自然语言描述解析为结构化配置 JSON。

输出格式：
{
  "challenger": "v2.3",
  "champion": "v2.2",
  "beta": "v2.4-Beta" 或 null,
  "sample_id": "consumer_2024q1q2" 或 "consumer_2024q1",
  "lookback_months": 6,
  "perf_window_months": 12,
  "ri_mode": "parceling",
  "language": "zh"
}

可用策略：v2.2（champion，固定），v2.3（challenger，固定），v2.4-Beta，v2.5-RC
可用样本：consumer_2024q1q2（主样本），consumer_2024q1（线下样本）"""

SYSTEM_NL_EN = """You are the configuration parsing assistant for BackTest Studio.

Parse the user's natural language description into a structured configuration JSON.

Output format:
{
  "challenger": "v2.3",
  "champion": "v2.2",
  "beta": "v2.4-Beta" or null,
  "sample_id": "consumer_2024q1q2" or "consumer_2024q1",
  "lookback_months": 6,
  "perf_window_months": 12,
  "ri_mode": "parceling",
  "language": "en"
}

Available strategies: v2.2 (champion, fixed), v2.3 (challenger, fixed), v2.4-Beta, v2.5-RC
Available samples: consumer_2024q1q2 (main), consumer_2024q1 (branch)"""


def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
    return "event: done\ndata: {}\n\n"


# ---------------------------------------------------------------------------
# Mock responses (no API key)
# ---------------------------------------------------------------------------

async def _mock_layer_analysis(layer: str, language: str) -> AsyncGenerator[str, None]:
    await asyncio.sleep(0.05)
    if language == "zh":
        findings = [
            f"{layer.upper()} 指标数据已完成计算，challenger v2.3 综合表现最佳",
            "v2.4-Beta 通过率最高但风险偏高，需关注合规问题",
            "v2.2 champion 表现稳定保守，RAROC 相对较低",
        ]
        warnings = [
            "v2.4-Beta 的 18-25 岁 DI Ratio=0.77，低于合规红线 0.80，需整改",
        ]
        recommendations = [
            "建议采用 v2.3 作为下一版本上线策略，RAROC 最优",
            "v2.4-Beta 需完善年轻客群公平性处理后再评估",
        ]
    else:
        findings = [
            f"{layer.upper()} metrics computed; v2.3 challenger shows best overall performance",
            "v2.4-Beta has highest approval rate but elevated risk and compliance concern",
            "v2.2 champion stable but conservative with lower RAROC",
        ]
        warnings = [
            "v2.4-Beta: age 18-25 DI Ratio=0.77, below compliance threshold 0.80",
        ]
        recommendations = [
            "Recommend v2.3 for production deployment based on best RAROC",
            "v2.4-Beta requires fairness remediation before further evaluation",
        ]

    yield _sse_line({"type": "thinking", "content": "正在分析指标数据..." if language == "zh" else "Analyzing metric data..."})
    await asyncio.sleep(0.1)
    yield _sse_line({
        "type": "result",
        "findings": findings,
        "warnings": warnings,
        "recommendations": recommendations,
    })
    yield _sse_done()


async def _mock_chat_reply(message: str, language: str) -> AsyncGenerator[str, None]:
    await asyncio.sleep(0.05)
    if language == "zh":
        reply = (
            "根据已计算的回测数据：v2.3 challenger 的 RAROC 为 22%，优于 champion v2.2 的 18%。"
            "通过率 38% 相比 v2.2 的 28% 提升 10pp，坏账率从 1.8% 上升至 2.4%。"
            "综合风险调整后收益，v2.3 是当前最优选择。"
        )
    else:
        reply = (
            "Based on computed backtest data: v2.3 challenger RAROC is 22%, outperforming "
            "champion v2.2 at 18%. Approval rate 38% vs 28% (+10pp), bad rate rises from "
            "1.8% to 2.4%. On a risk-adjusted basis, v2.3 is the optimal choice."
        )

    yield _sse_line({"type": "thinking", "content": "正在查询回测数据..." if language == "zh" else "Querying backtest data..."})
    await asyncio.sleep(0.1)
    yield _sse_line({"type": "reply", "content": reply})
    yield _sse_done()


async def _mock_parse_config(text: str, language: str) -> AsyncGenerator[str, None]:
    await asyncio.sleep(0.05)
    yield _sse_line({"type": "thinking", "content": "解析配置中..." if language == "zh" else "Parsing configuration..."})
    await asyncio.sleep(0.1)
    yield _sse_line({
        "type": "result",
        "config": {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": "v2.4-Beta",
            "sample_id": "consumer_2024q1q2",
            "lookback_months": 6,
            "perf_window_months": 12,
            "ri_mode": "parceling",
            "language": language,
        },
    })
    yield _sse_done()


async def _mock_report(run_id: str, language: str) -> AsyncGenerator[str, None]:
    await asyncio.sleep(0.05)
    yield _sse_line({"type": "thinking", "content": "生成报告中..." if language == "zh" else "Generating report..."})
    await asyncio.sleep(0.1)

    if language == "zh":
        content = f"""# BackTest Studio 回测报告

**Run ID**: {run_id}

## 执行摘要
本次回测对三个策略版本（v2.2 champion、v2.3 challenger、v2.4-Beta）进行全面对比分析。
综合 L1-L5 五层指标评估，v2.3 在风险调整后收益（RAROC=22%）和模型质量（AUC=0.742）方面表现最优。
v2.4-Beta 通过率最高（45%）但存在合规风险，18-25 岁客群 DI Ratio=0.77 低于监管红线 0.80。

## 模型质量（L1）
- v2.3 AUC=0.742，KS=0.312，优于 v2.2（AUC=0.718）
- Lift@20% 约 2.3x，模型区分度良好

## 业务价值（L2）
- v2.3 RAROC=22%，通过率 38%，为三策略最优风险收益比
- v2.4-Beta 通过率 45% 最高，但 RAROC 仅 16%

## 结论
建议以 v2.3 替换 v2.2 作为生产策略，预计可提升年化收益约 ¥12M。
v2.4-Beta 需完成公平性整改后再重新评估。
"""
    else:
        content = f"""# BackTest Studio Report

**Run ID**: {run_id}

## Executive Summary
This backtest compares three strategy versions (v2.2 champion, v2.3 challenger, v2.4-Beta) across L1-L5 metric layers.
v2.3 achieves the best risk-adjusted return (RAROC=22%) and model quality (AUC=0.742).
v2.4-Beta has the highest approval rate (45%) but carries compliance risk: age 18-25 DI Ratio=0.77, below the 0.80 threshold.

## Model Quality (L1)
- v2.3 AUC=0.742, KS=0.312 — outperforms v2.2 (AUC=0.718)
- Lift@20% ~2.3x, good discriminatory power

## Business Value (L2)
- v2.3 RAROC=22%, approval rate 38% — best risk-return ratio
- v2.4-Beta highest approval 45% but RAROC only 16%

## Conclusion
Recommend promoting v2.3 to replace v2.2 in production. Expected annual revenue uplift ~¥12M.
v2.4-Beta requires fairness remediation before re-evaluation.
"""

    yield _sse_line({"type": "chunk", "content": content})
    yield _sse_done()


async def _mock_compare(language: str) -> AsyncGenerator[str, None]:
    await asyncio.sleep(0.05)
    yield _sse_line({"type": "thinking", "content": "对比分析中..." if language == "zh" else "Running comparison..."})
    await asyncio.sleep(0.1)
    if language == "zh":
        findings = [
            "评分截断：v2.3 降至 650（基线 v2.2 为 680）；v2.4-Beta 取消硬门槛，仅靠 ML/反欺诈把关",
            "DTI 限额：v2.3 放宽至 0.68、v2.5-RC 0.70、v2.4-Beta 0.75（基线 0.60）",
            "提额与逾期窗口：v2.3 提额上限升至 +80%，零逾期要求由 MOB12 放宽至 MOB6",
        ]
        warnings = [
            "门槛与 DTI 放宽→通过率预计上升，但中分/高 DTI 边际客群坏账与滚动率可能升高",
            "v2.4-Beta 行为模型对薄文件年轻客群放量不足，年轻客群 DI 可能跌破 0.80 合规线",
        ]
        recommendations = [
            "对照 L2 通过率/RAROC 与 L3 坏账，验证放量是否得不偿失",
            "查看 L4 换入客群坏账与 L5 年轻客群 DI，确认质量与合规",
        ]
    else:
        findings = [
            "Score cutoff: v2.3 lowered to 650 (baseline v2.2 at 680); v2.4-Beta drops the hard cutoff, gating only via ML/anti-fraud",
            "DTI limit: relaxed to 0.68 (v2.3), 0.70 (v2.5-RC), 0.75 (v2.4-Beta) vs baseline 0.60",
            "Limit increase & delinquency window: v2.3 raises the cap to +80% and eases zero-delinquency from MOB12 to MOB6",
        ]
        warnings = [
            "Looser cutoff/DTI → approvals likely rise, but bad rate & roll rate may climb in the mid-score / high-DTI marginal band",
            "v2.4-Beta's behavioural model under-approves thin-file young applicants — their DI may fall below the 0.80 line",
        ]
        recommendations = [
            "Cross-check L2 approval/RAROC vs L3 bad rate to see if the expansion pays off",
            "Inspect L4 swap-in bad rate and L5 young-customer DI to confirm quality and compliance",
        ]

    yield _sse_line({
        "type": "result",
        "findings": findings,
        "warnings": warnings,
        "recommendations": recommendations,
    })
    yield _sse_done()


# ---------------------------------------------------------------------------
# Real DeepSeek streaming helpers
# ---------------------------------------------------------------------------

async def _stream_deepseek(
    messages: list[dict],
    language: str = "zh",
) -> AsyncGenerator[tuple[str, str], None]:
    """
    Stream from DeepSeek API. Yields (token_type, content) tuples
    where token_type is "thinking" or "answer".
    """
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

        stream = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            stream=True,
            # Sent via extra_body so the (older) openai SDK passes them through
            # to the request body instead of rejecting unknown kwargs.
            extra_body={"reasoning_effort": "high", "thinking": {"type": "enabled"}},
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # reasoning_content is DeepSeek-specific thinking tokens
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                yield ("thinking", delta.reasoning_content)

            if delta.content:
                yield ("answer", delta.content)
    except Exception as e:  # surface the real error instead of dropping the stream
        yield ("error", f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Public streaming functions
# ---------------------------------------------------------------------------

async def stream_parse_config(text: str, language: str = "zh") -> AsyncGenerator[str, None]:
    """
    Parse natural language into ExperimentConfig.
    Yields SSE-formatted strings.
    """
    if not settings.llm_available:
        async for chunk in _mock_parse_config(text, language):
            yield chunk
        return

    system = SYSTEM_NL_ZH if language == "zh" else SYSTEM_NL_EN
    user_msg = f"请将以下描述解析为配置 JSON：\n{text}" if language == "zh" else f"Parse the following into config JSON:\n{text}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    thinking_buf = ""
    answer_buf = ""

    async for token_type, content in _stream_deepseek(messages, language):
        if token_type == "thinking":
            thinking_buf += content
            yield _sse_line({"type": "thinking", "content": content})
        else:
            answer_buf += content

    # Parse JSON from answer
    try:
        # Extract JSON block if wrapped in markdown
        json_str = answer_buf
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        config = json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        # Fallback default config
        config = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": "v2.4-Beta",
            "sample_id": "consumer_2024q1q2",
            "lookback_months": 6,
            "perf_window_months": 12,
            "ri_mode": "parceling",
            "language": language,
        }

    yield _sse_line({"type": "result", "config": config})
    yield _sse_done()


async def stream_analyze_layer(
    run_id: str,
    layer: str,
    facts: dict,
    language: str = "zh",
) -> AsyncGenerator[str, None]:
    """
    Analyze a specific metric layer using pre-computed facts.
    Yields SSE-formatted strings.
    """
    if not settings.llm_available:
        async for chunk in _mock_layer_analysis(layer, language):
            yield chunk
        return

    system = SYSTEM_ZH if language == "zh" else SYSTEM_EN
    layer_names = {
        "l1": "L1 模型质量" if language == "zh" else "L1 Model Quality",
        "l2": "L2 业务价值" if language == "zh" else "L2 Business Value",
        "l3": "L3 风险指标" if language == "zh" else "L3 Risk Metrics",
        "l4": "L4 换组分析" if language == "zh" else "L4 Swap-set Analysis",
        "l5": "L5 公平性合规" if language == "zh" else "L5 Fairness & Compliance",
    }
    layer_name = layer_names.get(layer, layer.upper())

    if language == "zh":
        user_msg = (
            f"请对 run_id={run_id} 的回测结果进行 {layer_name} 分析。\n\n"
            f"facts（已计算指标，请勿推算额外数字）：\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
            "请输出 JSON 格式：{\"findings\": [...], \"warnings\": [...], \"recommendations\": [...]}"
        )
    else:
        user_msg = (
            f"Analyze {layer_name} for backtest run_id={run_id}.\n\n"
            f"facts (pre-computed metrics, do not derive additional numbers):\n{json.dumps(facts, indent=2)}\n\n"
            'Output JSON: {"findings": [...], "warnings": [...], "recommendations": [...]}'
        )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    answer_buf = ""
    err = None
    async for token_type, content in _stream_deepseek(messages, language):
        if token_type == "thinking":
            yield _sse_line({"type": "thinking", "content": content})
        elif token_type == "error":
            err = content
        else:
            answer_buf += content

    if err:
        yield _sse_line({
            "type": "result",
            "findings": [(f"AI 调用失败：{err}" if language == "zh" else f"AI call failed: {err}")],
            "warnings": [],
            "recommendations": [],
        })
        yield _sse_done()
        return

    try:
        json_str = answer_buf
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        result = json.loads(json_str)
        findings = result.get("findings", [])
        warnings = result.get("warnings", [])
        recommendations = result.get("recommendations", [])
    except (json.JSONDecodeError, IndexError):
        findings = ["数据不足" if language == "zh" else "Insufficient data"]
        warnings = []
        recommendations = []

    yield _sse_line({
        "type": "result",
        "findings": findings,
        "warnings": warnings,
        "recommendations": recommendations,
    })
    yield _sse_done()


async def stream_chat(
    run_id: str,
    message: str,
    history: list[dict],
    layer: Optional[str],
    facts: dict,
    language: str = "zh",
) -> AsyncGenerator[str, None]:
    """
    Stream interactive chat about a backtest run.
    """
    if not settings.llm_available:
        async for chunk in _mock_chat_reply(message, language):
            yield chunk
        return

    system = SYSTEM_CHAT_ZH if language == "zh" else SYSTEM_CHAT_EN
    context_prefix = f"回测 run_id={run_id}" if language == "zh" else f"Backtest run_id={run_id}"
    if layer:
        context_prefix += f", 当前层级={layer.upper()}" if language == "zh" else f", current layer={layer.upper()}"

    facts_str = json.dumps(facts, ensure_ascii=False, indent=2) if language == "zh" else json.dumps(facts, indent=2)
    system_with_facts = f"{system}\n\n{context_prefix}\n\nfacts:\n{facts_str}"

    _MAX_CHARS = 4000  # defence in depth: the schema also bounds these, but the
    #                    request goes to a third-party API we don't control.
    messages = [{"role": "system", "content": system_with_facts}]
    # Add conversation history (cap turns and per-message size)
    for h in history[-8:]:  # Keep last 8 turns
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:_MAX_CHARS]})
    messages.append({"role": "user", "content": message[:_MAX_CHARS]})

    answer_buf = ""
    async for token_type, content in _stream_deepseek(messages, language):
        if token_type == "thinking":
            yield _sse_line({"type": "thinking", "content": content})
        elif token_type == "error":
            answer_buf += (f"AI 调用失败：{content}" if language == "zh" else f"AI call failed: {content}")
        else:
            answer_buf += content

    yield _sse_line({"type": "reply", "content": answer_buf})
    yield _sse_done()


async def stream_report(
    run_id: str,
    facts: dict,
    language: str = "zh",
) -> AsyncGenerator[str, None]:
    """
    Stream a full Markdown report for a backtest run.
    """
    if not settings.llm_available:
        async for chunk in _mock_report(run_id, language):
            yield chunk
        return

    system = SYSTEM_REPORT_ZH if language == "zh" else SYSTEM_REPORT_EN
    facts_str = json.dumps(facts, ensure_ascii=False, indent=2) if language == "zh" else json.dumps(facts, indent=2)

    if language == "zh":
        user_msg = f"请为 run_id={run_id} 生成完整回测报告。\n\nfacts:\n{facts_str}"
    else:
        user_msg = f"Generate a complete backtest report for run_id={run_id}.\n\nfacts:\n{facts_str}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    async for token_type, content in _stream_deepseek(messages, language):
        if token_type == "thinking":
            yield _sse_line({"type": "thinking", "content": content})
        elif token_type == "error":
            yield _sse_line({"type": "chunk", "content": (f"\n\n**AI 调用失败：{content}**\n" if language == "zh" else f"\n\n**AI call failed: {content}**\n")})
        else:
            yield _sse_line({"type": "chunk", "content": content})

    yield _sse_done()


async def stream_compare_strategies(
    facts: dict,
    language: str = "zh",
) -> AsyncGenerator[str, None]:
    """
    Stream multi-strategy comparison analysis.
    """
    if not settings.llm_available:
        async for chunk in _mock_compare(language):
            yield chunk
        return

    system = SYSTEM_COMPARE_ZH if language == "zh" else SYSTEM_COMPARE_EN
    facts_str = json.dumps(facts, ensure_ascii=False, indent=2) if language == "zh" else json.dumps(facts, indent=2)

    if language == "zh":
        user_msg = (
            "请对比以下策略的【设计与规则】差异（挑战者 vs 冠军/基线 vs 对照β），逐项说明每个策略相对基线改了什么，"
            "聚焦评分截断、DTI、评分卡权重、反欺诈、决策表分流、客群分叉、提额区间等。不要评判指标优劣或谁更好。\n\n"
            f"facts(策略定义)：\n{facts_str}\n\n"
            "输出 JSON：{\"findings\": [...], \"warnings\": [...], \"recommendations\": [...]}"
        )
    else:
        user_msg = (
            "Compare the DESIGN and RULES of these strategies (challenger vs champion/baseline vs control β). "
            "State item by item what each changed vs the baseline — score cutoff, DTI, scorecard weights, anti-fraud, "
            "decision-table routing, bifurcation, limit-increase range. Do not judge metric quality or which is better.\n\n"
            f"facts (strategy definitions):\n{facts_str}\n\n"
            'Output JSON: {"findings": [...], "warnings": [...], "recommendations": [...]}'
        )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    answer_buf = ""
    err = None
    async for token_type, content in _stream_deepseek(messages, language):
        if token_type == "thinking":
            yield _sse_line({"type": "thinking", "content": content})
        elif token_type == "error":
            err = content
        else:
            answer_buf += content

    if err:
        yield _sse_line({
            "type": "result",
            "findings": [(f"AI 调用失败：{err}" if language == "zh" else f"AI call failed: {err}")],
            "warnings": [],
            "recommendations": [],
        })
        yield _sse_done()
        return

    try:
        json_str = answer_buf
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        result = json.loads(json_str)
        findings = result.get("findings", [])
        warnings = result.get("warnings", [])
        recommendations = result.get("recommendations", [])
    except (json.JSONDecodeError, IndexError):
        findings = ["数据不足" if language == "zh" else "Insufficient data"]
        warnings = []
        recommendations = []

    yield _sse_line({
        "type": "result",
        "findings": findings,
        "warnings": warnings,
        "recommendations": recommendations,
    })
    yield _sse_done()
