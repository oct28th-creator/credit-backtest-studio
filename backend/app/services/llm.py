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
3. 语言：简洁、专业、有结构。输出 JSON，包含 findings（洞察）、warnings（预警）、recommendations（建议）三个数组。
4. 每条 findings/warnings/recommendations 最多 60 字。
5. 若 facts 中数据不足，说明"数据不足"，禁止猜测。
6. 三策略对比时，明确指出每个策略的相对排名和幅度差异。"""

SYSTEM_EN = """You are the credit strategy analysis assistant for BackTest Studio.

HARD CONSTRAINTS:
1. Never compute or estimate any metric. All numbers must come verbatim from the facts field.
2. Every conclusion must be traceable to specific data in facts.
3. Output JSON with findings, warnings, recommendations arrays (max 60 chars each).
4. If data in facts is insufficient, state "insufficient data" — never guess.
5. When comparing 3 strategies, explicitly state relative ranking and magnitude differences."""

SYSTEM_COMPARE_ZH = """你是 BackTest Studio 的策略对比助手。

任务：对比挑战者、冠军(基线)与对照β(如有)在【策略设计与规则】上的差异，帮助用户快速理解它们到底"哪里不一样"。

【硬性约束】
1. 只对比策略的规则与配置差异：评分截断(score_cutoff)、DTI 限额、评分卡特征与权重、反欺诈版本与规则、IF-ELSE、决策表分流、客群分叉、提额区间、上线时间等。
2. 不要评价指标结果(KS/AUC/RAROC/不良率/DI 等)的好坏，也不要下"哪个策略更优"的结论——指标优劣由"指标解读"负责，这里只做设计层面的对比。
3. 所有差异必须基于 facts 中的策略定义，逐项、可对照，说明每个策略相对基线改了什么。
4. 输出 JSON：findings(关键设计差异，逐条对比)、warnings(设计层面值得关注的取舍或客群结构变化，不含指标优劣判断)、recommendations(从对比角度建议重点关注哪些规则变更)。每条≤60字。"""

SYSTEM_COMPARE_EN = """You are the strategy-comparison assistant for BackTest Studio.

Task: compare the challenger, champion (baseline) and control β (if any) on their DESIGN AND RULES, so the user quickly understands how they actually differ.

HARD CONSTRAINTS:
1. Only compare rule/config differences: score_cutoff, DTI limit, scorecard features & weights, anti-fraud version & rules, IF-ELSE, decision table routing, segment bifurcation, limit-increase range, go-live date, etc.
2. Do NOT judge metric results (KS/AUC/RAROC/bad rate/DI) as good or bad, and do NOT conclude which strategy is better — metric quality is the job of the per-layer metrics analysis; here you only compare design.
3. Every difference must be grounded in the strategy definitions in facts, item by item, stating what each strategy changed vs the baseline.
4. Output JSON: findings (key design differences, item by item), warnings (design trade-offs or customer-mix shifts worth noting, no metric judgments), recommendations (which rule changes to watch from a comparison standpoint). Max 60 chars each."""

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
            "评分截断：挑战者 v2.3 下调至 620（基线 v2.2 为 680），更积极获取中分客群",
            "DTI 限额：v2.3 放宽至 0.45（基线 0.60 口径不同），并升级反欺诈至 AF-v3",
            "决策表：v2.3 在中分段对挑战者放量，提额区间较基线上调",
        ]
        warnings = [
            "对照 β（如 v2.4-Beta）进一步放宽截断/DTI 并对年轻客群放量，客群结构变化最大",
        ]
        recommendations = [
            "重点关注评分截断与 DTI 两项规则变更带来的客群迁移",
            "对反欺诈版本差异（AF-v2→AF-v3）评估前端拦截口径是否一致",
        ]
    else:
        findings = [
            "Score cutoff: challenger v2.3 lowered to 620 (baseline v2.2 at 680), acquiring more mid-score customers",
            "DTI limit: v2.3 relaxed to 0.45 and anti-fraud upgraded to AF-v3",
            "Decision table: v2.3 opens up mid-score bands; limit-increase range raised vs baseline",
        ]
        warnings = [
            "Control β (e.g. v2.4-Beta) further loosens cutoff/DTI and expands young customers — largest mix shift",
        ]
        recommendations = [
            "Watch customer migration driven by the score-cutoff and DTI changes",
            "Check whether the anti-fraud change (AF-v2→AF-v3) keeps front-end interception consistent",
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

    messages = [{"role": "system", "content": system_with_facts}]
    # Add conversation history
    for h in history[-8:]:  # Keep last 8 turns
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

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
