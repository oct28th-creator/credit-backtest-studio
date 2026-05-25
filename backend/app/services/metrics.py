"""
Full L1-L5 metric calculations.

This module orchestrates the metric computation for a full backtest run,
calling into fixtures.py for the actual math.
"""
from __future__ import annotations

import time
import hashlib
import numpy as np
from collections import OrderedDict
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


# Module-level LRU cache: (sample_id, seed) → np.ndarray.
# Bounded so repeated runs with many distinct seeds can't grow without limit.
_DATA_CACHE: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
_DATA_CACHE_MAX = 8


def get_sample_data(sample_id: str = "consumer_2024q1q2", seed: int = 42) -> np.ndarray:
    """Return (cached) synthetic data for a given sample configuration."""
    key = (sample_id, seed)
    if key in _DATA_CACHE:
        _DATA_CACHE.move_to_end(key)
        return _DATA_CACHE[key]

    sample_meta = next((s for s in SAMPLES if s["id"] == sample_id), None)
    n = sample_meta["n_rows"] if sample_meta else 50000
    # Use a smaller n for perf — cap at 80k for fast response
    n = min(n, 80000)
    _DATA_CACHE[key] = generate_synthetic_data(n=n, seed=seed)
    if len(_DATA_CACHE) > _DATA_CACHE_MAX:
        _DATA_CACHE.popitem(last=False)
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


# --------------------------------------------------------------------------- #
# Custom backtest orchestration (uploaded strategies / datasets)
# --------------------------------------------------------------------------- #
def _is_builtin_ref(ref: Optional[str]) -> bool:
    return bool(ref) and ref.startswith("builtin:")


def _ref_id(ref: str) -> str:
    return ref.split(":", 1)[1] if ":" in ref else ref


def _build_result_for_ref(ref: str, view, df_struct):
    """Return a StrategyResult for a strategy ref against the given DataView.

    builtin:<id>  -> reuse the built-in adapter (needs the structured array).
    custom:<id>   -> run the uploaded code in the sandbox.
    """
    from app.db import repository
    from app.strategies.builtin_adapter import build_builtin_result
    from app.strategies.contract import StrategyResult
    from app.strategies.sandbox import run_strategy

    if _is_builtin_ref(ref):
        if df_struct is None:
            raise ValueError(
                f"builtin strategy '{ref}' cannot run on a custom dataset; "
                "upload it as a custom strategy instead"
            )
        return build_builtin_result(df_struct, _ref_id(ref))

    sid = _ref_id(ref)
    rec = repository.get_custom_strategy(sid)
    if rec is None:
        raise ValueError(f"custom strategy not found: {sid}")
    meta = rec.get("meta", {})
    required = meta.get("required_inputs", []) or []
    params = {k: (v.get("default") if isinstance(v, dict) else v)
              for k, v in (meta.get("params") or {}).items()}
    features = view.as_feature_dict(required)
    pd_hat, approve_mask = run_strategy(rec["code_text"], features, params)
    if len(pd_hat) != len(view):
        raise ValueError(
            f"strategy output length {len(pd_hat)} does not match dataset rows {len(view)}"
        )
    info = {
        "id": sid,
        "name": meta.get("name", sid),
        "version": meta.get("version", ""),
        "role": meta.get("role", "challenger"),
        "params": meta.get("params", {}),
    }
    return StrategyResult(approve_mask=approve_mask, pd_hat=pd_hat, strategy_info=info)


def run_backtest_custom(
    champion_ref: str,
    challenger_ref: str,
    beta_ref: Optional[str],
    dataset_ref: str,
    mapping_id: Optional[str] = None,
) -> dict:
    """Run a backtest using strategy/dataset *refs* of the form
    ``builtin:<id>`` or ``custom:<id>``.

    When everything is built-in (dataset + all strategies) this delegates to the
    legacy ``run_backtest`` so results stay byte-identical with the original path.
    """
    from app.services import custom_metrics
    from app.strategies.contract import DataView

    refs = [r for r in (champion_ref, challenger_ref, beta_ref) if r]
    all_builtin = _is_builtin_ref(dataset_ref) and all(_is_builtin_ref(r) for r in refs)
    if all_builtin:
        return run_backtest(
            champion_id=_ref_id(champion_ref),
            challenger_id=_ref_id(challenger_ref),
            beta_id=_ref_id(beta_ref) if beta_ref else None,
            sample_id=_ref_id(dataset_ref),
        )

    t0 = time.time()

    # ── Dataset / view ──────────────────────────────────────────────────
    df_struct = None
    if _is_builtin_ref(dataset_ref):
        df_struct = get_sample_data(_ref_id(dataset_ref))
        data = {name: df_struct[name] for name in df_struct.dtype.names}
        # identity mapping: built-in column names map outcome->bad etc.
        view = DataView(data, mapping={}, role_columns={"outcome": "bad", "score": "score",
                                                        "gender": "gender", "age_band": "age_band",
                                                        "channel": "channel"})
    else:
        view, _roles = custom_metrics.load_dataset_as_view(_ref_id(dataset_ref), mapping_id)

    # ── Strategy results per ref ────────────────────────────────────────
    champion_result = _build_result_for_ref(champion_ref, view, df_struct)
    challenger_result = _build_result_for_ref(challenger_ref, view, df_struct)
    beta_result = _build_result_for_ref(beta_ref, view, df_struct) if beta_ref else None

    ref_results = {champion_ref: champion_result, challenger_ref: challenger_result}
    if beta_ref:
        ref_results[beta_ref] = beta_result

    strategy_ids = [champion_ref, challenger_ref]
    if beta_ref:
        strategy_ids.append(beta_ref)

    layers: dict[str, dict] = {}
    for ref, res in ref_results.items():
        layers[ref] = custom_metrics.apply_custom_strategy(view, res, champion_result)

    layers["_swap_chall_vs_champ"] = custom_metrics.compute_l4(view, challenger_result, champion_result)
    if beta_result is not None:
        layers["_swap_beta_vs_champ"] = custom_metrics.compute_l4(view, beta_result, champion_result)

    summary = []
    for ref in strategy_ids:
        r = layers[ref]
        summary.append({
            "strategy_id": ref,
            "strategy_name": r["strategy_info"].get("name", ref),
            "approval_rate": r["l2"].get("approval_rate"),
            "bad_rate": r["l2"].get("bad_rate"),
            "raroc": r["l2"].get("raroc"),
            "avg_profit": r["l2"].get("avg_profit_per_approved"),
            "auc": r["l1"].get("auc"),
            "ks": r["l1"].get("ks"),
            "fpd_rate": r["l3"].get("fpd_rate"),
            "has_compliance_issue": r["l5"].get("has_compliance_issue", False),
        })
    layers["_summary"] = summary

    duration = time.time() - t0
    snap_input = f"{champion_ref}|{challenger_ref}|{beta_ref}|{dataset_ref}|{mapping_id}"
    snapshot_sha = hashlib.sha256(snap_input.encode()).hexdigest()[:12]

    return {
        "duration_s": round(duration, 3),
        "sample_size": len(view),
        "snapshot_sha": snapshot_sha,
        "layers": layers,
        "strategy_ids": strategy_ids,
    }
