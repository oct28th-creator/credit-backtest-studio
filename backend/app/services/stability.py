"""
Population Stability Index (PSI) and Characteristic Stability Index (CSI) calculations.
"""
from __future__ import annotations

import hashlib
import numpy as np
from typing import Optional

from app.data.fixtures import generate_synthetic_data, _approve_mask, STRATEGIES


def _psi_single(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """
    Compute PSI between two arrays.

    PSI = sum((actual% - expected%) * ln(actual% / expected%))
    < 0.10: stable, 0.10-0.25: moderate shift, > 0.25: major shift
    """
    eps = 1e-8
    # Use quantile bins from expected distribution
    quantiles = np.linspace(0, 1, bins + 1)
    bin_edges = np.quantile(expected, quantiles)
    bin_edges[0] -= eps
    bin_edges[-1] += eps

    exp_counts, _ = np.histogram(expected, bins=bin_edges)
    act_counts, _ = np.histogram(actual, bins=bin_edges)

    exp_pct = exp_counts / (exp_counts.sum() + eps)
    act_pct = act_counts / (act_counts.sum() + eps)

    # Clip to avoid log(0)
    exp_pct = np.clip(exp_pct, eps, None)
    act_pct = np.clip(act_pct, eps, None)

    psi = float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))
    return round(psi, 5)


def compute_psi_trend(
    strategy_id: str,
    feature: str = "score",
    n_months: int = 6,
    seed: int = 42,
) -> list[dict]:
    """
    Compute month-over-month PSI for a feature under a given strategy.

    Simulates 6 monthly cohorts with small distribution drift.
    """
    rng = np.random.default_rng(
        int(hashlib.md5(f"{strategy_id}_{feature}_{seed}".encode()).hexdigest(), 16) % (2**32)
    )

    # Base distribution (month 0 = reference)
    base_df = generate_synthetic_data(n=5000, seed=seed)
    approved_base = _approve_mask(base_df, strategy_id)
    base_values = base_df[feature][approved_base].astype(float)

    trend = []
    for m in range(1, n_months + 1):
        # Each month, add a small drift to simulate population shift
        drift_seed = int(seed + m * 997 + hash(strategy_id) % 10000)
        month_df = generate_synthetic_data(n=5000, seed=drift_seed % (2**32))
        approved_month = _approve_mask(month_df, strategy_id)
        month_values = month_df[feature][approved_month].astype(float)

        if len(base_values) < 10 or len(month_values) < 10:
            psi_val = 0.0
        else:
            psi_val = _psi_single(base_values, month_values)

        # Interpretation
        if psi_val < 0.10:
            status = "stable"
        elif psi_val < 0.25:
            status = "moderate_shift"
        else:
            status = "major_shift"

        trend.append({
            "month": f"M{m}",
            "psi": psi_val,
            "status": status,
            "n_reference": int(approved_base.sum()),
            "n_current": int(approved_month.sum()),
        })

    return trend


def compute_csi(
    strategy_id: str,
    features: Optional[list[str]] = None,
    seed: int = 42,
) -> list[dict]:
    """
    Compute Characteristic Stability Index for key numeric features.

    Returns one CSI entry per feature.
    """
    if features is None:
        features = ["score", "dti"]

    base_df = generate_synthetic_data(n=5000, seed=seed)
    compare_df = generate_synthetic_data(n=5000, seed=seed + 1)

    results = []
    for feat in features:
        if feat not in base_df.dtype.names:
            continue
        base_vals = base_df[feat].astype(float)
        comp_vals = compare_df[feat].astype(float)
        csi_val = _psi_single(base_vals, comp_vals)

        results.append({
            "feature": feat,
            "csi": csi_val,
            "stable": csi_val < 0.10,
        })

    return results


def compute_score_distribution(
    strategy_id: str,
    df: Optional[np.ndarray] = None,
    seed: int = 42,
    bins: int = 20,
) -> dict:
    """
    Compute score distribution for approved vs rejected populations.
    Returns histogram data for visualization.
    """
    if df is None:
        df = generate_synthetic_data(seed=seed)

    approved = _approve_mask(df, strategy_id)
    scores_appr = df["score"][approved].astype(float)
    scores_rej = df["score"][~approved].astype(float)

    bin_edges = np.linspace(520, 840, bins + 1)

    def _hist(vals: np.ndarray) -> list[dict]:
        counts, edges = np.histogram(vals, bins=bin_edges)
        return [
            {
                "score_low": int(edges[i]),
                "score_high": int(edges[i + 1]),
                "count": int(counts[i]),
                "pct": round(float(counts[i] / (vals.sum() + 1e-8)), 4),
            }
            for i in range(len(counts))
        ]

    return {
        "strategy_id": strategy_id,
        "approved_distribution": _hist(scores_appr),
        "rejected_distribution": _hist(scores_rej),
        "approved_mean": round(float(scores_appr.mean()), 1) if len(scores_appr) > 0 else 0,
        "rejected_mean": round(float(scores_rej.mean()), 1) if len(scores_rej) > 0 else 0,
    }
