"""Deterministic conclusions.

Three things a person reads a backtest to learn, computed from the numbers
rather than narrated by a model:

  decompose_swap()  where a challenger's gain actually came from — model
                    discrimination, or a loosened policy
  find_fix()        the nearest knob setting that clears a tripped guardrail
  build_bundle()    everything an approval committee needs, in one document

The language model's job downstream is to say these in a sentence, not to
work them out. A number a model derived is a number nobody can audit.
"""
from __future__ import annotations

from typing import Optional

# A rule difference is "model discrimination" when it moves the score cutoff,
# and "policy" when it relaxes a hard gate. The distinction decides which
# approval path a change goes down, so it is worth being explicit about.
_MODEL_RULES = {"风险评分不足"}
_POLICY_RULES = {"负债率过高", "近期逾期记录", "薄文件/行为不足"}


def decompose_swap(matrix: dict) -> Optional[dict]:
    """Split a challenger's swap-in gain into model-driven and policy-driven.

    Reads the swap-in attribution: each admitted account is filed under the
    champion rule that had declined it. Accounts the champion declined on its
    model score are won by better discrimination; accounts it declined on a
    hard gate are won by relaxing that gate.
    """
    rows = matrix.get("swap_in_attribution") or []
    if not rows:
        return None
    total = sum(r["n"] for r in rows)
    if total == 0:
        return None

    def bucket(names: set) -> dict:
        sel = [r for r in rows if r["reason"] in names]
        n = sum(r["n"] for r in sel)
        bad = (sum(r["n"] * r["bad_rate"] for r in sel) / n) if n else None
        return {"n": n, "share": round(n / total, 4),
                "bad_rate": round(bad, 4) if bad is not None else None,
                "rules": [{"reason": r["reason"], "rule": r["rule"], "n": r["n"],
                           "bad_rate": r["bad_rate"]} for r in sel]}

    model = bucket(_MODEL_RULES)
    policy = bucket(_POLICY_RULES)
    other_n = total - model["n"] - policy["n"]

    driver = "model" if model["share"] >= 0.6 else "policy" if policy["share"] >= 0.6 else "mixed"
    swap_out = matrix.get("swap_out") or {}
    swap_in = matrix.get("swap_in") or {}

    return {
        "total_swap_in": total,
        "model_driven": model,
        "policy_driven": policy,
        "other_n": other_n,
        "driver": driver,
        "swap_in_bad_rate": swap_in.get("bad_rate"),
        "swap_out_bad_rate": swap_out.get("bad_rate"),
        "swap_in_raroc": matrix.get("swap_in_raroc"),
        "headline": _headline(driver, model, policy, swap_in, swap_out),
    }


def _headline(driver: str, model: dict, policy: dict,
              swap_in: dict, swap_out: dict) -> str:
    si_bad = swap_in.get("bad_rate")
    so_bad = swap_out.get("bad_rate")
    tail = ""
    if si_bad is not None and so_bad is not None:
        tail = (f"；换入客群坏账 {si_bad:.2%}，换出客群坏账 {so_bad:.2%}"
                + ("，即多批的比拒掉的更干净" if si_bad < so_bad else ""))
    if driver == "model":
        return (f"增量的 {model['share']:.0%} 来自模型区分度提升（被旧模型评分拦下、"
                f"被新模型重新排序的客群），只有 {policy['share']:.0%} 来自政策放宽{tail}。"
                f"这条路径按模型升级审批，不按政策放松审批。")
    if driver == "policy":
        return (f"增量的 {policy['share']:.0%} 来自放宽硬性门槛，模型贡献仅 "
                f"{model['share']:.0%}{tail}。这是政策放松，需要走额度政策审批。")
    return (f"增量中模型贡献 {model['share']:.0%}、政策放宽贡献 {policy['share']:.0%}，"
            f"两者都不占主导{tail}。拆开各自评估后再定审批路径。")


# --------------------------------------------------------------------------- #
# Guardrail repair
# --------------------------------------------------------------------------- #
# Which knob to move for which finding, and in which direction relief lies.
_REPAIR_PLAYBOOK = {
    "disparate_impact": ("target_approval_rate", "either",
                         "调整目标通过率会同时改变各群体的准入比例"),
    "bad_rate_ceiling": ("target_approval_rate", "down",
                         "收紧准入，把边际高风险客群挡在外面"),
    "approved_book_too_small": ("target_approval_rate", "up",
                                "放开准入以取得统计上可用的核准户数"),
}


def repair_candidates(code: str, current: float) -> Optional[dict]:
    """A knob and a set of values to try for a tripped guardrail."""
    entry = _REPAIR_PLAYBOOK.get(code)
    if entry is None:
        return None
    knob, direction, why = entry
    steps = [0.05 * i for i in range(1, 7)]
    if direction == "down":
        values = [round(current - s, 3) for s in steps]
    elif direction == "up":
        values = [round(current + s, 3) for s in steps]
    else:
        values = [round(current + d * s, 3) for s in steps for d in (-1, 1)]
    values = [v for v in values if 0.05 <= v <= 0.95]
    # nearest first: the smallest change that clears the finding is the answer
    values.sort(key=lambda v: abs(v - current))
    return {"knob": knob, "values": values[:8], "why": why, "current": current}


# --------------------------------------------------------------------------- #
# Why a group is being declined
# --------------------------------------------------------------------------- #
_GROUP_MASKS = {
    "young_core": ("age_band", 0),
    "female_male": ("gender", 1),
    "outsider_local": ("channel", 2),
}


def explain_group_gap(df, strategy_id: str, group_key: str,
                      overrides: Optional[dict] = None) -> Optional[dict]:
    """Which of a strategy's rules declines the affected group, and how much
    more often than it declines everyone else.

    When a knob sweep cannot clear a disparate-impact finding, this is the
    reason: the gap is coming from a hard gate, not from where the cutoff
    sits, and no threshold move will touch it.
    """
    from app.data.fixtures import _gate_attribution, _approve_mask

    spec = _GROUP_MASKS.get(group_key)
    if spec is None or df is None:
        return None
    col, value = spec
    if col not in (df.dtype.names or ()):
        return None

    in_group = df[col] == value
    approved = _approve_mask(df, strategy_id, overrides)
    grp_rej = in_group & ~approved
    ref_rej = ~in_group & ~approved
    if grp_rej.sum() == 0 or ref_rej.sum() == 0:
        return None

    grp = {r["reason"]: r["pct"] for r in _gate_attribution(df, grp_rej, strategy_id, overrides)}
    ref = {r["reason"]: r["pct"] for r in _gate_attribution(df, ref_rej, strategy_id, overrides)}

    rows = []
    for reason in set(grp) | set(ref):
        g, r = grp.get(reason, 0.0), ref.get(reason, 0.0)
        rows.append({"reason": reason, "group_pct": round(g, 4),
                     "reference_pct": round(r, 4), "gap_pp": round((g - r) * 100, 2)})
    rows.sort(key=lambda x: -x["gap_pp"])
    top = rows[0] if rows else None
    return {
        "group": group_key,
        "by_reason": rows,
        "dominant_reason": top["reason"] if top else None,
        "note": (f"该群体被拒的主因是「{top['reason']}」，占其拒绝原因的 "
                 f"{top['group_pct']:.0%}，比参照群体高 {top['gap_pp']:.1f}pp"
                 if top and top["gap_pp"] > 0 else None),
    }
