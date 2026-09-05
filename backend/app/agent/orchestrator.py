"""Designer → Executor → Analyst → Critic.

The one place an LLM sits in the loop. The split matters:

  Designer  turns a goal into a *bounded* set of experiment configs
  Executor  runs them through the same path as any human-submitted run
  Analyst   reads the compact metric table and states findings
  Critic    attacks those findings, armed with deterministic guardrail output

The Critic exists because a single model asked to both find and validate a
result will validate it. It is given the guardrail verdict (sample size,
significance, disparate impact) as facts it cannot override, and its job is to
downgrade the conclusion when those facts warrant it.

Every step degrades to a deterministic fallback when no API key is configured,
so the loop is testable and demo-able offline.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from app.agent import budget as budget_mod
from app.agent import guardrails, tools
from app.services import llm

logger = logging.getLogger("backtest.agent")

MAX_EXPERIMENTS_PER_PLAN = 8


def _event(phase: str, **payload) -> dict:
    return {"phase": phase, **payload}


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
_DESIGNER_ZH = """你是信贷策略回测平台的实验设计者。把用户目标翻译成一组**可执行、可证伪**的实验。

规则：
- 只能通过 policy_overrides 调整白名单旋钮：{knobs}
- 可选策略：{strategies}
- 最多 {max_exp} 个实验，每个实验必须回答假设的一个具体侧面；不要重复同一配置
- 必须包含一个基线（不加任何 override）作为对照
- 变量一次只动一个，除非你明确说明为什么需要联动

只输出 JSON：
{{"hypothesis": "可证伪的假设陈述",
  "stop_condition": "什么结果会让你判定假设不成立",
  "experiments": [{{"label": "简短标签",
                   "config_patch": {{"policy_overrides": {{"v2.3": {{"target_approval_rate": 0.5}}}}}},
                   "why": "这个实验单独回答了什么"}}]}}"""

_ANALYST_ZH = """你是信贷策略分析师。基于给定的实验结果表给出发现。

要求：
- 只使用表中出现的数字，不要推断未给出的指标
- 比率类字段是 0-1 小数，呈现时 ×100 加 %
- 指出指标之间的权衡（通过率↑通常伴随坏账↑），不要只报最优点
- 如果数据不足以支持结论，明确说不足

只输出 JSON：
{{"findings": ["一条一个发现"],
  "best_option": {{"run_id": "...", "strategy": "...", "why": "..."}},
  "tradeoffs": ["..."],
  "data_gaps": ["..."]}}"""

_CRITIC_ZH = """你是对抗性审稿人。你的任务是**削弱**下面的结论，而不是附和它。

必须逐项检查：
1. 样本量与统计显著性（p 值、核准户数）
2. 多重比较：跑了 N 个实验后出现"显著"是否只是抽样噪声
3. 单一随机种子：结论是否只在这一次抽样成立
4. 公平性红线（DI、TPR 差异）
5. 结论是否超出仿真环境能力：当前只有历史回放，没有拒绝推断、没有行为反馈，
   任何关于"长期客群变化"的推断都不成立
6. 过拟合：旋钮是否被调到只在这份数据上好看

guardrail_report 中的 blocking 项是硬事实，你不能推翻，必须在 verdict 中体现。

只输出 JSON：
{{"verdict": "supported | partially_supported | not_supported | inconclusive",
  "confidence": 0.0,
  "issues": [{{"severity": "high|medium|low", "issue": "...", "implication": "..."}}],
  "what_would_settle_it": ["还需要做什么实验才能定论"]}}"""

_DESIGNER_EN = _DESIGNER_ZH  # prompts are language-tagged by the user message


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
async def _design(goal: str, base_config: dict, session: budget_mod.Session,
                  language: str, strategies: list[str], knobs: list[str]) -> dict:
    max_exp = min(session.remaining_experiments(), MAX_EXPERIMENTS_PER_PLAN)
    system = _DESIGNER_ZH.format(knobs=sorted(knobs), strategies=strategies, max_exp=max_exp)
    user = (f"目标：{goal}\n\n基础配置：{base_config}\n"
            f"回答语言：{'中文' if language == 'zh' else 'English'}")
    try:
        session.spend_llm_call()
        plan = await llm.complete_json(system, user)
        plan["experiments"] = (plan.get("experiments") or [])[:max_exp]
        if not plan["experiments"]:
            raise llm.LLMUnavailable("designer returned no experiments")
        plan["source"] = "llm"
        return plan
    except llm.LLMUnavailable as exc:
        logger.info("designer falling back to deterministic plan: %s", exc)
        return _fallback_plan(goal, base_config, max_exp)


def _fallback_plan(goal: str, base_config: dict, max_exp: int) -> dict:
    """Deterministic plan: baseline plus a cutoff sweep on the challenger.

    Not a stand-in for reasoning — it is the honest default when no model is
    configured, and it keeps the loop exercisable end to end."""
    challenger = base_config.get("challenger") or "v2.3"
    experiments = [{"label": "baseline", "config_patch": {},
                    "why": "对照组：不加任何 override 的当前配置"}]
    for value in [0.35, 0.50, 0.60][: max(max_exp - 1, 0)]:
        experiments.append({
            "label": f"{challenger}@{int(value * 100)}%",
            "config_patch": {"policy_overrides": {challenger: {"target_approval_rate": value}}},
            "why": f"把 {challenger} 的目标通过率移到 {value:.0%}，观察 RAROC 与坏账的权衡",
        })
    return {
        "hypothesis": f"（无模型，默认计划）围绕目标「{goal}」扫描 {challenger} 的通过率-收益权衡",
        "stop_condition": "若 RAROC 随通过率单调下降，则放宽通过率不成立",
        "experiments": experiments[:max_exp],
        "source": "fallback",
    }


async def _analyse(goal: str, plan: dict, table: dict, language: str,
                   session: budget_mod.Session) -> dict:
    user = (f"目标：{goal}\n假设：{plan.get('hypothesis')}\n\n"
            f"实验结果表：{table}\n回答语言：{'中文' if language == 'zh' else 'English'}")
    try:
        session.spend_llm_call()
        out = await llm.complete_json(_ANALYST_ZH, user)
        out["source"] = "llm"
        return out
    except llm.LLMUnavailable as exc:
        logger.info("analyst falling back: %s", exc)
        return _fallback_findings(table)


def _fallback_findings(table: dict) -> dict:
    rows = [r for r in table.get("rows", []) if r.get("raroc") is not None]
    best = max(rows, key=lambda r: r["raroc"]) if rows else None
    findings = []
    if best:
        findings.append(
            f"RAROC 最高的是 run {best['run_id']} 的 {best['strategy']}："
            f"RAROC {best['raroc']:.2%}，通过率 {(best.get('approval_rate') or 0):.2%}，"
            f"坏账率 {(best.get('bad_rate') or 0):.2%}"
        )
        apr = [r for r in rows if r.get("approval_rate") is not None]
        if len(apr) >= 2:
            lo, hi = min(apr, key=lambda r: r["approval_rate"]), max(apr, key=lambda r: r["approval_rate"])
            findings.append(
                f"通过率从 {lo['approval_rate']:.2%} 提到 {hi['approval_rate']:.2%} 时，"
                f"坏账率从 {(lo.get('bad_rate') or 0):.2%} 变为 {(hi.get('bad_rate') or 0):.2%}"
            )
    return {
        "findings": findings or ["实验结果不足以给出发现"],
        "best_option": ({"run_id": best["run_id"], "strategy": best["strategy"],
                         "why": "RAROC 最高"} if best else None),
        "tradeoffs": ["通过率与坏账率的权衡需要结合资本成本判断"],
        "data_gaps": ["未做多种子重复，无法给出置信区间"],
        "source": "fallback",
    }


async def _critique(plan: dict, table: dict, findings: dict, guardrail_report: dict,
                    n_experiments: int, session: budget_mod.Session) -> dict:
    user = (f"假设：{plan.get('hypothesis')}\n实验数：{n_experiments}\n"
            f"结果表：{table}\n分析结论：{findings}\n"
            f"guardrail_report：{guardrail_report}")
    try:
        session.spend_llm_call()
        out = await llm.complete_json(_CRITIC_ZH, user, temperature=0.1)
        out["source"] = "llm"
    except llm.LLMUnavailable as exc:
        logger.info("critic falling back: %s", exc)
        out = _fallback_critique(guardrail_report, n_experiments)

    # Deterministic override: a blocking guardrail cannot be talked past.
    if guardrail_report.get("n_blocking"):
        out["verdict"] = "not_supported"
        out["confidence"] = min(float(out.get("confidence", 0.3) or 0.3), 0.3)
        out.setdefault("issues", []).insert(0, {
            "severity": "high",
            "issue": "guardrail 阻断项存在",
            "implication": "该结果不得作为候选策略推进，无论分析结论如何",
        })
    return out


def _fallback_critique(guardrail_report: dict, n_experiments: int) -> dict:
    issues = [{"severity": "high" if b.get("severity") == "block" else "medium",
               "issue": b.get("detail"), "implication": "结论受限"}
              for b in guardrail_report.get("blocking", []) + guardrail_report.get("warnings", [])]
    if n_experiments >= 5:
        issues.append({
            "severity": "medium",
            "issue": f"共跑了 {n_experiments} 个实验，未做多重比较校正",
            "implication": "出现「显著」结果的概率被高估，需要 Bonferroni/FDR 校正",
        })
    issues.append({
        "severity": "high",
        "issue": "当前仿真环境只有历史回放（无拒绝推断、无行为反馈）",
        "implication": "任何关于长期客群迁移或政策放开后客群变化的推断都不成立",
    })
    return {
        "verdict": "inconclusive" if guardrail_report.get("n_blocking") else "partially_supported",
        "confidence": 0.4,
        "issues": issues,
        "what_would_settle_it": [
            "同一配置换 3-5 个 seed 重复，给出置信区间",
            "对最优点做拒绝推断（P3 能力）后重算长期坏账",
        ],
        "source": "fallback",
    }


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
async def investigate(
    goal: str,
    base_config: dict,
    session: budget_mod.Session,
    language: str = "zh",
) -> AsyncGenerator[dict, None]:
    """Run one full agent investigation, yielding an event per phase."""
    yield _event("session", session=session.to_dict(), goal=goal)

    # ── prior work: never spend compute on a question already answered ──
    try:
        prior = await tools.call("search_experiments", {"query": goal[:40], "limit": 5})
    except Exception as exc:  # noqa: BLE001
        prior = {"runs": [], "error": str(exc)}
    yield _event("prior_work", **prior)

    # ── design ──────────────────────────────────────────────────────────
    catalogue = await tools.call("list_strategies")
    strategy_ids = [s["id"] for s in catalogue["builtin"]]
    knobs = catalogue["builtin"][0]["knobs"] if catalogue["builtin"] else []
    plan = await _design(goal, base_config, session, language, strategy_ids, knobs)
    yield _event("plan", plan=plan)

    # ── execute ─────────────────────────────────────────────────────────
    run_ids: list[str] = []
    for exp in plan["experiments"]:
        try:
            result = await tools.call("submit_experiment", {
                "config": {**base_config, **_patch_of(exp)},
                "hypothesis": f"{plan.get('hypothesis')} | {exp.get('label')}: {exp.get('why')}",
                "tags": ["agent", f"session:{session.session_id}"],
            }, session=session)
        except budget_mod.BudgetExceeded as exc:
            yield _event("budget_stop", detail=str(exc))
            break
        except Exception as exc:  # noqa: BLE001 — one bad config must not kill the loop
            yield _event("experiment_failed", label=exp.get("label"), error=str(exc))
            continue
        run_ids.append(result["run_id"])
        yield _event("experiment", label=exp.get("label"), **result)

    if not run_ids:
        yield _event("done", status="no_runs",
                     summary="没有成功执行的实验，无法给出结论", session=session.to_dict())
        return

    # ── guardrails (deterministic, before any narrative) ────────────────
    checks = [await tools.call("check_guardrails", {"run_id": rid}) for rid in run_ids]
    report = guardrails.summarize(checks)
    yield _event("guardrails", report=report)

    # ── analyse ─────────────────────────────────────────────────────────
    table = await tools.call("compare_runs", {"run_ids": run_ids})
    yield _event("comparison", table=table)

    findings = await _analyse(goal, plan, table, language, session)
    yield _event("findings", findings=findings)

    # ── critique ────────────────────────────────────────────────────────
    critique = await _critique(plan, table, findings, report, len(run_ids), session)
    yield _event("critique", critique=critique)

    # ── record: the registry is the deliverable, not the chat message ───
    conclusion = _conclusion_text(findings, critique)
    for rid in run_ids:
        try:
            await tools.call("annotate_run", {
                "run_id": rid, "conclusion": conclusion,
                "tags": ["agent", f"session:{session.session_id}",
                         f"verdict:{critique.get('verdict')}"],
            })
        except Exception:  # noqa: BLE001 — annotation is best-effort
            logger.exception("failed to annotate run %s", rid)

    session.status = "completed"
    yield _event("done", status="completed", run_ids=run_ids,
                 verdict=critique.get("verdict"), conclusion=conclusion,
                 session=session.to_dict())


def _patch_of(exp: dict) -> dict:
    patch = exp.get("config_patch") or {}
    return patch if isinstance(patch, dict) else {}


def _conclusion_text(findings: dict, critique: dict) -> str:
    head = "；".join((findings.get("findings") or [])[:2]) or "无明确发现"
    verdict = critique.get("verdict", "inconclusive")
    top_issue = (critique.get("issues") or [{}])[0].get("issue", "")
    return f"[{verdict}] {head}" + (f"｜主要保留：{top_issue}" if top_issue else "")
