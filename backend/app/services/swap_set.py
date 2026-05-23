"""
Swap-set analysis: 4-quadrant comparison of challenger vs champion decisions.
"""
from __future__ import annotations

import numpy as np
from typing import Optional

from app.data.fixtures import generate_synthetic_data, _approve_mask, STRATEGIES


def compute_swap_set(
    challenger_id: str,
    champion_id: str,
    df: Optional[np.ndarray] = None,
    seed: int = 42,
) -> dict:
    """
    Compute the 4-quadrant swap-set matrix.

    Quadrants:
      - Double Approve: both challenger and champion approve
      - Swap-in:        challenger approves, champion rejects (challenger-only)
      - Swap-out:       challenger rejects, champion approves (champion-only)
      - Double Reject:  both reject
    """
    if df is None:
        df = generate_synthetic_data(seed=seed)

    if challenger_id not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {challenger_id}")
    if champion_id not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {champion_id}")

    chall_mask = _approve_mask(df, challenger_id)
    champ_mask = _approve_mask(df, champion_id)

    da_mask = chall_mask & champ_mask          # Double approve
    si_mask = chall_mask & ~champ_mask         # Swap-in (challenger only)
    so_mask = ~chall_mask & champ_mask         # Swap-out (champion only)
    dr_mask = ~chall_mask & ~champ_mask        # Double reject

    bad = df["bad"].astype(int)
    n = len(df)

    def _stats(mask: np.ndarray) -> dict:
        sub_bad = bad[mask]
        count = int(mask.sum())
        return {
            "n": count,
            "pct": round(count / n, 4),
            "bad_rate": round(float(sub_bad.mean()), 4) if count > 0 else 0.0,
            "bad_count": int(sub_bad.sum()),
        }

    da = _stats(da_mask)
    si = _stats(si_mask)
    so = _stats(so_mask)
    dr = _stats(dr_mask)

    consistency_pct = round((da["n"] + dr["n"]) / n, 4)

    # Score band breakdown
    score_bands = [
        ("≤640", 520, 640),
        ("641-680", 641, 680),
        ("681-720", 681, 720),
        (">720", 720, 841),
    ]

    band_analysis = []
    for label, lo, hi in score_bands:
        band_mask = (df["score"] >= lo) & (df["score"] < hi)
        n_band = int(band_mask.sum())
        if n_band == 0:
            continue

        agree = int(((chall_mask == champ_mask) & band_mask).sum())
        chall_apr = int((chall_mask & band_mask).sum())
        champ_apr = int((champ_mask & band_mask).sum())
        si_band = int((si_mask & band_mask).sum())
        so_band = int((so_mask & band_mask).sum())

        band_analysis.append({
            "score_band": label,
            "n": n_band,
            "consistency_pct": round(agree / n_band, 4),
            "challenger_approval_rate": round(chall_apr / n_band, 4),
            "champion_approval_rate": round(champ_apr / n_band, 4),
            "swap_in_n": si_band,
            "swap_out_n": so_band,
            "swap_in_bad_rate": round(float(bad[si_mask & band_mask].mean()), 4)
                if (si_mask & band_mask).sum() > 0 else 0.0,
            "swap_out_bad_rate": round(float(bad[so_mask & band_mask].mean()), 4)
                if (so_mask & band_mask).sum() > 0 else 0.0,
        })

    # Channel breakdown
    channel_labels = {0: "Online", 1: "Branch", 2: "Partner"}
    channel_analysis = []
    for ch_val, ch_label in channel_labels.items():
        ch_mask = df["channel"] == ch_val
        n_ch = int(ch_mask.sum())
        if n_ch == 0:
            continue
        agree_ch = int(((chall_mask == champ_mask) & ch_mask).sum())
        si_ch = int((si_mask & ch_mask).sum())
        so_ch = int((so_mask & ch_mask).sum())

        channel_analysis.append({
            "channel": ch_label,
            "n": n_ch,
            "consistency_pct": round(agree_ch / n_ch, 4),
            "swap_in_n": si_ch,
            "swap_out_n": so_ch,
        })

    # Incremental value of swap-in population
    # Revenue gain vs risk cost for customers only challenger would approve
    avg_loan = 8000.0
    margin_rate = 0.18
    lgd = 0.55
    si_revenue = si["n"] * avg_loan * margin_rate
    si_el = si["n"] * avg_loan * si["bad_rate"] * lgd
    si_net = si_revenue - si_el

    so_revenue = so["n"] * avg_loan * margin_rate
    so_el = so["n"] * avg_loan * so["bad_rate"] * lgd
    so_net = so_revenue - so_el

    return {
        "challenger": challenger_id,
        "champion": champion_id,
        "n_total": n,
        "double_approve": da,
        "swap_in": si,
        "swap_out": so,
        "double_reject": dr,
        "consistency_pct": consistency_pct,
        "score_band_analysis": band_analysis,
        "channel_analysis": channel_analysis,
        "incremental_value": {
            "swap_in_gross_revenue": round(si_revenue, 0),
            "swap_in_expected_loss": round(si_el, 0),
            "swap_in_net_value": round(si_net, 0),
            "swap_out_gross_revenue": round(so_revenue, 0),
            "swap_out_expected_loss": round(so_el, 0),
            "swap_out_net_value": round(so_net, 0),
            "net_challenger_advantage": round(si_net - so_net, 0),
        },
    }


def compute_three_way_swap(
    challenger_id: str,
    champion_id: str,
    beta_id: str,
    df: Optional[np.ndarray] = None,
    seed: int = 42,
) -> dict:
    """
    Three-way decision comparison across challenger, champion, and beta.
    Returns pairwise swap sets.
    """
    if df is None:
        df = generate_synthetic_data(seed=seed)

    chall_vs_champ = compute_swap_set(challenger_id, champion_id, df)
    beta_vs_champ = compute_swap_set(beta_id, champion_id, df)
    beta_vs_chall = compute_swap_set(beta_id, challenger_id, df)

    return {
        "challenger_vs_champion": chall_vs_champ,
        "beta_vs_champion": beta_vs_champ,
        "beta_vs_challenger": beta_vs_chall,
    }
