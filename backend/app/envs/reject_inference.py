"""Reject inference — and, more usefully, its error bar.

The production problem: you only observe repayment for applicants you
approved. Everyone the champion declined has no outcome, so any claim about
"what would have happened if we had approved them" is an estimate.

This module reproduces that condition on the synthetic book *on purpose*:

    1. hide the outcome for everyone the champion rejected
    2. estimate it back with the chosen method (``ri_mode``)
    3. compare the estimate to the label we deliberately hid

Step 3 is the point. Every credit shop runs step 2 and reports the number as
if it were a measurement; almost none report how far off the method is. On
this book we know the truth, so a run can carry its own error bar — and the
guardrails can refuse a conclusion whose method is off by more than the effect
it claims to have found.

Modes (``ExperimentConfig.ri_mode``):
  none          ignore rejects entirely — the naive, downward-biased baseline
  parceling     assign each rejected applicant the observed bad rate of its
                score band, scaled by a penalty factor (industry rule of thumb)
  fuzzy         each reject contributes fractionally: p_bad bad + (1-p_bad) good,
                using the strategy's own calibrated pd̂
  augmentation  reweight approved applicants by the inverse of their band's
                acceptance rate, then apply those rates to the rejects
"""
from __future__ import annotations

import numpy as np

MODES = ("none", "parceling", "fuzzy", "augmentation")

# Parceling penalty: rejects in a band default worse than the accepted
# population of the same band (they were declined for reasons the band does
# not capture). 2.0 is the common desk convention, not a fitted value.
PARCELING_PENALTY = 2.0

_BANDS = [(0, 600), (600, 650), (650, 700), (700, 750), (750, 10_000)]


def _band_index(scores: np.ndarray) -> np.ndarray:
    idx = np.zeros(len(scores), dtype=np.int8)
    for i, (lo, hi) in enumerate(_BANDS):
        idx[(scores >= lo) & (scores < hi)] = i
    return idx


def estimate_bad(
    df: np.ndarray,
    observed_mask: np.ndarray,
    target_mask: np.ndarray,
    pd_hat: np.ndarray,
    mode: str = "parceling",
) -> np.ndarray:
    """Estimated probability of bad for each row in ``target_mask``.

    ``observed_mask`` is the population whose outcome is visible (what the
    champion approved). Returns an array aligned to ``target_mask`` rows.
    """
    if mode not in MODES:
        raise ValueError(f"unknown ri_mode: {mode}; expected one of {MODES}")

    bands = _band_index(df["score"])
    bad = df["bad"].astype(float)
    n_target = int(target_mask.sum())
    if n_target == 0:
        return np.array([], dtype=float)

    if mode == "none":
        # Rejects contribute nothing. Kept as an explicit mode because it is
        # what a backtest does by default, and naming it makes the bias visible.
        return np.zeros(n_target, dtype=float)

    if mode == "fuzzy":
        return np.clip(pd_hat[target_mask].astype(float), 0.0, 1.0)

    # Band-based methods: observed bad rate per score band on the approved book
    observed_rate = np.zeros(len(_BANDS), dtype=float)
    pop_rate = float(bad[observed_mask].mean()) if observed_mask.any() else float(bad.mean())
    for b in range(len(_BANDS)):
        sel = observed_mask & (bands == b)
        observed_rate[b] = float(bad[sel].mean()) if sel.sum() >= 50 else pop_rate

    if mode == "parceling":
        rates = np.clip(observed_rate * PARCELING_PENALTY, 0.0, 1.0)
    else:  # augmentation — weight by how rarely the band was accepted
        rates = np.zeros(len(_BANDS), dtype=float)
        for b in range(len(_BANDS)):
            in_band = bands == b
            n_band = int(in_band.sum())
            accepted = int((observed_mask & in_band).sum())
            accept_rate = accepted / n_band if n_band else 1.0
            # Inverse-acceptance weight, capped so a band accepted twice does
            # not dominate the estimate.
            weight = min(1.0 / accept_rate, 4.0) if accept_rate > 0 else 4.0
            rates[b] = min(observed_rate[b] * weight, 1.0)

    return rates[bands[target_mask]]


def report(
    df: np.ndarray,
    champion_mask: np.ndarray,
    strategy_masks: dict,
    pd_hats: dict,
    mode: str = "parceling",
) -> dict:
    """Run the mask → estimate → compare cycle and report the method's error.

    ``strategy_masks`` maps strategy id to its approval mask; the interesting
    population per strategy is its swap-in set (approved here, rejected by the
    champion) — exactly the accounts a backtest has no data for.
    """
    rejected = ~champion_mask
    bad = df["bad"].astype(float)

    out: dict = {
        "mode": mode,
        "n_observed": int(champion_mask.sum()),
        "n_masked": int(rejected.sum()),
        "strategies": {},
    }

    for sid, mask in strategy_masks.items():
        swap_in = mask & rejected
        n_swap = int(swap_in.sum())
        if n_swap == 0:
            out["strategies"][sid] = {"n_swap_in": 0, "note": "无 swap-in 客群，无需推断"}
            continue

        est = estimate_bad(df, champion_mask, swap_in, pd_hats[sid], mode)
        estimated = float(est.mean()) if len(est) else 0.0
        oracle = float(bad[swap_in].mean())
        bias_pp = (estimated - oracle) * 100

        out["strategies"][sid] = {
            "n_swap_in": n_swap,
            "estimated_bad_rate": round(estimated, 4),
            "oracle_bad_rate": round(oracle, 4),
            "bias_pp": round(bias_pp, 3),
            "relative_error": round(abs(bias_pp / 100) / oracle, 3) if oracle > 0 else None,
            "direction": "低估" if bias_pp < 0 else "高估",
        }

    errors = [s.get("relative_error") for s in out["strategies"].values()
              if s.get("relative_error") is not None]
    out["max_relative_error"] = round(max(errors), 3) if errors else None
    out["note"] = (
        "oracle 仅在合成账簿上可得：真实生产环境没有这一列。此处的 bias 用于"
        "标定方法误差，不是对生产数据的承诺。"
    )
    return out


def compare_modes(
    df: np.ndarray,
    champion_mask: np.ndarray,
    strategy_masks: dict,
    pd_hats: dict,
) -> dict:
    """Same population, every method — which one is least wrong on this book."""
    per_mode = {m: report(df, champion_mask, strategy_masks, pd_hats, m) for m in MODES}
    ranked = sorted(
        ((m, r.get("max_relative_error")) for m, r in per_mode.items()),
        key=lambda kv: (kv[1] is None, kv[1] if kv[1] is not None else 0),
    )
    return {"modes": per_mode, "ranked": [{"mode": m, "max_relative_error": e} for m, e in ranked]}
