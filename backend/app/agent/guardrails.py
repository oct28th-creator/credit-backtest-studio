"""Deterministic checks an agent cannot argue with.

An LLM reading metrics will happily call a strategy "the clear winner" when
the swap-set difference is not significant, the approved book has 40 accounts,
or the disparate-impact ratio is 0.61. These checks run on the numbers, not on
the narrative, and the orchestrator injects their verdict into the Critic step
and attaches it to the conclusion.

Two severities:
  block — the result must not be presented as a candidate strategy
  warn  — the result stands but the caveat must travel with it
"""
from __future__ import annotations

from typing import Optional

BLOCK = "block"
WARN = "warn"

# Four-fifths rule (US EEOC, widely used as a fairness screen in credit too).
DEFAULT_THRESHOLDS: dict[str, float] = {
    "di_min": 0.80,             # disparate impact ratio floor
    "tpr_gap_max": 0.10,        # true-positive-rate gap between groups
    "min_approved": 500,        # below this the book is too small to conclude
    "min_sample": 5000,         # below this the whole slice is thin
    "max_bad_rate": 0.06,       # business risk ceiling on the approved book
    "min_auc": 0.60,            # below this the model barely ranks
    "max_swap_p_value": 0.05,   # swap-set difference must be significant
    "max_target_approval": 0.90,  # a sweep asking for ~everyone approved
    "max_ri_relative_error": 0.50,  # reject-inference method error ceiling
}

# Attributes that must never be model inputs. Checked against an uploaded
# strategy's declared required_inputs.
FORBIDDEN_INPUTS = {
    "gender", "sex", "race", "ethnicity", "religion", "marital_status",
    "nationality", "disability", "pregnancy", "sexual_orientation",
    "性别", "种族", "宗教", "婚姻状况", "国籍",
}

_GROUP_LABELS = {
    "female_male": "female vs male",
    "young_core": "18-25 vs 26-55",
    "outsider_local": "partner vs online",
}


def _finding(code: str, severity: str, detail: str, **extra) -> dict:
    return {"code": code, "severity": severity, "detail": detail, **extra}


def _kpi(layer: dict, version: str) -> dict:
    for k in layer.get("kpis", []) or []:
        if k.get("version") == version:
            return k
    return {}


def check_run(run: dict, thresholds: Optional[dict] = None) -> dict:
    """Screen one completed run. Returns {run_id, ok, blocking, warnings}."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    layers = run.get("layers", {}) or {}
    sample_size = int(run.get("sample_size", 0) or 0)
    versions = [v for v in [run.get("challenger"), run.get("champion"), run.get("beta")] if v]

    blocking: list[dict] = []
    warnings: list[dict] = []

    # ── sample adequacy ────────────────────────────────────────────────
    if sample_size and sample_size < th["min_sample"]:
        warnings.append(_finding(
            "thin_sample", WARN,
            f"样本仅 {sample_size} 行，低于 {int(th['min_sample'])}，结论置信度低",
            value=sample_size, threshold=th["min_sample"],
        ))

    for v in versions:
        l2 = _kpi(layers.get("l2", {}), v)
        l1 = _kpi(layers.get("l1", {}), v)

        if not l2:
            # No L2 row for this strategy in this run — nothing to screen.
            # Absent metrics must never be read as zero metrics.
            continue
        approval = float(l2.get("approval_rate", 0) or 0)
        n_approved = int(approval * sample_size)
        if sample_size and n_approved < th["min_approved"]:
            blocking.append(_finding(
                "approved_book_too_small", BLOCK,
                f"{v} 核准账户仅 {n_approved} 户，低于 {int(th['min_approved'])}，"
                f"坏账率无统计意义",
                strategy=v, value=n_approved, threshold=th["min_approved"],
            ))

        bad_rate = float(l2.get("el", 0) or 0)
        if bad_rate > th["max_bad_rate"]:
            warnings.append(_finding(
                "bad_rate_ceiling", WARN,
                f"{v} 坏账率 {bad_rate:.2%} 超过风险上限 {th['max_bad_rate']:.0%}",
                strategy=v, value=bad_rate, threshold=th["max_bad_rate"],
            ))

        auc = float(l1.get("auc", 0) or 0)
        if auc and auc < th["min_auc"]:
            warnings.append(_finding(
                "weak_discrimination", WARN,
                f"{v} AUC {auc:.3f} 低于 {th['min_auc']}，模型区分度不足",
                strategy=v, value=auc, threshold=th["min_auc"],
            ))

    # ── fairness ───────────────────────────────────────────────────────
    for v, groups in (layers.get("l5", {}).get("di_by_group", {}) or {}).items():
        for key, ratio in (groups or {}).items():
            try:
                ratio = float(ratio)
            except (TypeError, ValueError):
                continue
            if ratio and ratio < th["di_min"]:
                blocking.append(_finding(
                    "disparate_impact", BLOCK,
                    f"{v} 在「{_GROUP_LABELS.get(key, key)}」上 DI={ratio:.2f}，"
                    f"低于四分之五规则阈值 {th['di_min']:.2f}",
                    strategy=v, group=key, value=ratio, threshold=th["di_min"],
                ))

    tpr_gap = abs(float((layers.get("l5", {}).get("kpis", {}) or {}).get("tpr_gap", 0) or 0))
    if tpr_gap > th["tpr_gap_max"]:
        warnings.append(_finding(
            "tpr_gap", WARN,
            f"TPR 组间差异 {tpr_gap:.3f} 超过 {th['tpr_gap_max']}",
            value=tpr_gap, threshold=th["tpr_gap_max"],
        ))

    # ── statistical significance of the swap set ───────────────────────
    for v, matrix in (layers.get("l4", {}).get("matrices", {}) or {}).items():
        p = matrix.get("p_value")
        if p is not None and float(p) > th["max_swap_p_value"]:
            warnings.append(_finding(
                "swap_not_significant", WARN,
                f"{v} 与冠军策略的 swap-set 坏账差异 p={float(p):.3f}，"
                f"不显著，不能据此宣称更优",
                strategy=v, value=float(p), threshold=th["max_swap_p_value"],
            ))

    # ── configuration sanity ───────────────────────────────────────────
    config = run.get("config", {}) or {}
    for sid, ov in (config.get("policy_overrides") or {}).items():
        tar = ov.get("target_approval_rate")
        if tar is not None and float(tar) > th["max_target_approval"]:
            warnings.append(_finding(
                "extreme_override", WARN,
                f"{sid} 目标通过率被设为 {float(tar):.0%}，已接近全批，"
                f"该点位的结论不具备业务意义",
                strategy=sid, value=float(tar), threshold=th["max_target_approval"],
            ))

    blocking.extend(_check_forbidden_inputs(config))
    b, w = _check_environment(run.get("environment") or {}, th)
    blocking.extend(b)
    warnings.extend(w)

    return {
        "run_id": run.get("run_id"),
        "ok": not blocking,
        "blocking": blocking,
        "warnings": warnings,
        "thresholds": th,
    }


def _check_environment(env: dict, th: dict) -> tuple:
    """The world a run assumed bounds what it may be used to claim.

    Under reject inference we know how wrong the method is on this book, so a
    conclusion resting on an estimate with larger error than the effect it
    reports gets blocked rather than footnoted."""
    blocking: list[dict] = []
    warnings: list[dict] = []
    if not env:
        return blocking, warnings

    if env.get("level") == "L0a":
        warnings.append(_finding(
            "replay_only_environment", WARN,
            "本次运行使用历史回放环境：拒绝客群无表现数据、无行为反馈，"
            "任何关于放开准入后客群变化的推断都不成立",
            value=env.get("id"),
        ))

    ri = env.get("reject_inference") or {}
    err = ri.get("max_relative_error")
    if err is not None:
        if err > th["max_ri_relative_error"]:
            blocking.append(_finding(
                "reject_inference_unreliable", BLOCK,
                f"拒绝推断方法「{ri.get('mode')}」在本账簿上的相对误差达 {err:.0%}，"
                f"超过 {th['max_ri_relative_error']:.0%}：swap-in 客群风险的结论不可用，"
                f"先用 compare_ri_modes 换方法",
                value=err, threshold=th["max_ri_relative_error"],
            ))
        elif err > th["max_ri_relative_error"] / 2:
            warnings.append(_finding(
                "reject_inference_noisy", WARN,
                f"拒绝推断相对误差 {err:.0%}，结论需带误差区间表述",
                value=err,
            ))
    return blocking, warnings


def _check_forbidden_inputs(config: dict) -> list[dict]:
    """A custom strategy must not read a protected attribute as a feature."""
    from app.db import repository

    out: list[dict] = []
    refs = [config.get(k) for k in ("champion_ref", "challenger_ref", "beta_ref")]
    for ref in [r for r in refs if r and str(r).startswith("custom:")]:
        rec = repository.get_custom_strategy(str(ref).split(":", 1)[1])
        if not rec:
            continue
        inputs = {str(x).lower() for x in (rec.get("meta", {}) or {}).get("required_inputs", [])}
        hits = sorted(inputs & FORBIDDEN_INPUTS)
        if hits:
            out.append(_finding(
                "protected_attribute_as_input", BLOCK,
                f"策略 {ref} 将受保护属性 {hits} 作为模型输入",
                strategy=ref, value=hits,
            ))
    return out


def summarize(checks: list[dict]) -> dict:
    """Fold per-run checks into one verdict for a whole experiment batch."""
    blocking = [b for c in checks for b in c.get("blocking", [])]
    warnings = [w for c in checks for w in c.get("warnings", [])]
    return {
        "ok": not blocking,
        "n_runs_checked": len(checks),
        "n_blocking": len(blocking),
        "n_warnings": len(warnings),
        "blocking": blocking,
        "warnings": warnings,
    }
