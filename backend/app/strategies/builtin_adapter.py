"""Adapter that wraps the existing built-in strategies as StrategyResult objects.

Built-in behaviour must stay bit-for-bit identical: this simply reuses the
fixtures helpers (`_approve_mask`, `_model_score`, `STRATEGIES`).
"""
from __future__ import annotations

import numpy as np

from app.data.fixtures import STRATEGIES, _approve_mask, _model_score
from app.strategies.contract import StrategyResult


def build_builtin_result(df: np.ndarray, strategy_id: str) -> StrategyResult:
    if strategy_id not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_id}")
    mask = _approve_mask(df, strategy_id)
    pd_hat = _model_score(df, strategy_id).astype(np.float64)
    info = dict(STRATEGIES[strategy_id])
    info.setdefault("params", {
        "limit_increase_min": info.get("limit_increase_min"),
        "limit_increase_max": info.get("limit_increase_max"),
    })
    return StrategyResult(
        approve_mask=np.asarray(mask, dtype=bool),
        pd_hat=np.clip(pd_hat, 0.0, 1.0),
        strategy_info=info,
    )
