"""
Full L1-L5 metric calculations.

This module orchestrates the metric computation for a full backtest run,
calling into fixtures.py for the actual math.
"""
from __future__ import annotations

import time
import hashlib
import numpy as np
from typing import Optional

from app.data.fixtures import (
    STRATEGIES,
    SAMPLES,
    generate_synthetic_data,
    apply_strategy,
    _approve_mask,
    _compute_l1,
    _compute_l2,
    _compute_l3,
    _compute_l4,
    _compute_l5,
)


# Module-level cache: (sample_id, seed) → np.ndarray
_DATA_CACHE: dict[tuple, np.ndarray] = {}


def get_sample_data(sample_id: str = "consumer_2024q1q2", seed: int = 42) -> np.ndarray:
    """Return (cached) synthetic data for a given sample configuration."""
    key = (sample_id, seed)
    if key not in _DATA_CACHE:
        sample_meta = next((s for s in SAMPLES if s["id"] == sample_id), None)
        n = sample_meta["n_rows"] if sample_meta else 50000
        # Use a smaller n for perf — cap at 80k for fast response
        n = min(n, 80000)
        _DATA_CACHE[key] = generate_synthetic_data(n=n, seed=seed)
    return _DATA_CACHE[key]


def run_backtest(
    champion_id: str,
    challenger_id: str,
    beta_id: Optional[str],
    sample_id: str,
    slice_dim: Optional[str] = None,
    slice_value: Optional[str] = None,
) -> dict:
    """
    Run a full backtest across all strategies and all L1-L5 layers.

    Returns a structured dict with per-strategy results and a summary.
    """
    t0 = time.time()
    df = get_sample_data(sample_id)

    # Apply optional slice filtering
    if slice_dim and slice_value:
        df = _apply_slice(df, slice_dim, slice_value)

    strategy_ids = [champion_id, challenger_id]
    if beta_id and beta_id in STRATEGIES:
        strategy_ids.append(beta_id)

    results: dict[str, dict] = {}
    for sid in strategy_ids:
        results[sid] = apply_strategy(df, sid, champion_id=champion_id)

    # Challenger vs champion swap set (always computed)
    l4_chall_vs_champ = _compute_l4(df, challenger_id, champion_id)

    # Beta vs champion (if beta exists)
    l4_beta_vs_champ = None
    if beta_id and beta_id in STRATEGIES:
        l4_beta_vs_champ = _compute_l4(df, beta_id, champion_id)

    # Build layers dict: keyed by strategy_id, then l1..l5
    layers: dict[str, dict] = {}
    for sid in strategy_ids:
        layers[sid] = results[sid]

    # Add cross-strategy L4 explicitly
    layers["_swap_chall_vs_champ"] = l4_chall_vs_champ
    if l4_beta_vs_champ:
        layers["_swap_beta_vs_champ"] = l4_beta_vs_champ

    # Summary KPI table for quick comparison
    summary = _build_summary(results, strategy_ids)
    layers["_summary"] = summary

    duration = time.time() - t0

    # Deterministic snapshot hash (strategy ids + sample)
    snap_input = f"{champion_id}|{challenger_id}|{beta_id}|{sample_id}"
    snapshot_sha = hashlib.sha256(snap_input.encode()).hexdigest()[:12]

    return {
        "duration_s": round(duration, 3),
        "sample_size": len(df),
        "snapshot_sha": snapshot_sha,
        "layers": layers,
        "strategy_ids": strategy_ids,
    }


def _apply_slice(df: np.ndarray, slice_dim: str, slice_value: str) -> np.ndarray:
    """Filter dataframe to a dimension slice."""
    dim_map = {
        "gender": ("gender", {"male": 0, "female": 1}),
        "channel": ("channel", {"online": 0, "branch": 1, "partner": 2}),
        "age_band": ("age_band", {"18-25": 0, "26-35": 1, "36-45": 2, "46-55": 3, "56+": 4}),
        "vintage_q": ("vintage_q", {"2023Q3": 0, "2023Q4": 1, "2024Q1": 2, "2024Q2": 3}),
    }
    if slice_dim not in dim_map:
        return df
    field, value_map = dim_map[slice_dim]
    if slice_value not in value_map:
        return df
    val = value_map[slice_value]
    mask = df[field] == val
    return df[mask]


def _build_summary(results: dict[str, dict], strategy_ids: list[str]) -> list[dict]:
    """Build a KPI comparison table row per strategy."""
    rows = []
    for sid in strategy_ids:
        r = results[sid]
        rows.append({
            "strategy_id": sid,
            "strategy_name": STRATEGIES[sid]["name"],
            "approval_rate": r["l2"].get("approval_rate"),
            "bad_rate": r["l2"].get("bad_rate"),
            "raroc": r["l2"].get("raroc"),
            "avg_profit": r["l2"].get("avg_profit_per_approved"),
            "auc": r["l1"].get("auc"),
            "ks": r["l1"].get("ks"),
            "fpd_rate": r["l3"].get("fpd_rate"),
            "has_compliance_issue": r["l5"].get("has_compliance_issue", False),
        })
    return rows
