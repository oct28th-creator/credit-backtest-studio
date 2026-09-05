"""Multi-seed replication.

One backtest is one draw. "v2.3 的 RAROC 比 v2.2 高 4 个点" may be a property
of the strategy or a property of that particular sample — a single run cannot
tell you which, and every agent-generated conclusion in this platform is built
on single runs unless something forces the question.

This module reruns a configuration across seeds and reports mean, spread and —
the part that matters — whether the *ranking* between strategies survives
resampling. A result that flips ordering across seeds is noise wearing a
decimal point.
"""
from __future__ import annotations

import statistics
from typing import Optional

_METRICS = ("approval_rate", "bad_rate", "raroc", "auc", "ks")


def _extract(compact: dict) -> dict:
    return {sid: {m: s.get(m) for m in _METRICS}
            for sid, s in (compact.get("strategies") or {}).items()}


def aggregate(compacts: list, seeds: list) -> dict:
    """Fold per-seed compact metrics into mean/std/range plus a stability call."""
    if not compacts:
        return {"seeds": seeds, "n": 0, "strategies": {}, "stable": None}

    per_strategy: dict = {}
    for compact in compacts:
        for sid, metrics in _extract(compact).items():
            slot = per_strategy.setdefault(sid, {m: [] for m in _METRICS})
            for m, v in metrics.items():
                if v is not None:
                    slot[m].append(float(v))

    summary: dict = {}
    for sid, series in per_strategy.items():
        summary[sid] = {}
        for m, values in series.items():
            if not values:
                continue
            mean = statistics.fmean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0.0
            summary[sid][m] = {
                "mean": round(mean, 5),
                "std": round(std, 5),
                "min": round(min(values), 5),
                "max": round(max(values), 5),
                # 95% interval on the mean, normal approximation. Wide is a
                # finding, not a defect.
                "ci95": [round(mean - 1.96 * std / (len(values) ** 0.5), 5),
                         round(mean + 1.96 * std / (len(values) ** 0.5), 5)] if len(values) > 1 else None,
                "n": len(values),
            }

    ranking = _ranking_stability(compacts, "raroc")
    return {
        "seeds": seeds,
        "n": len(compacts),
        "strategies": summary,
        "ranking_by_raroc": ranking,
        "stable": ranking.get("consistent"),
        "verdict": _verdict(ranking, summary),
    }


def _ranking_stability(compacts: list, metric: str) -> dict:
    orders = []
    for compact in compacts:
        rows = [(sid, s.get(metric)) for sid, s in (compact.get("strategies") or {}).items()
                if s.get(metric) is not None]
        if rows:
            orders.append(tuple(sid for sid, _ in sorted(rows, key=lambda kv: -kv[1])))
    if not orders:
        return {"consistent": None, "orders": []}
    unique = sorted(set(orders))
    return {
        "metric": metric,
        "consistent": len(unique) == 1,
        "orders": [list(o) for o in unique],
        "winner": orders[0][0] if len(unique) == 1 else None,
    }


def _verdict(ranking: dict, summary: dict) -> str:
    if ranking.get("consistent") is None:
        return "无足够数据判断稳健性"
    if not ranking["consistent"]:
        return (f"排序在不同随机种子下发生翻转（观察到 {len(ranking['orders'])} 种排序），"
                f"该结论是抽样噪声，不能作为策略优劣依据")
    winner = ranking.get("winner")
    raroc = (summary.get(winner) or {}).get("raroc") or {}
    spread = raroc.get("max", 0) - raroc.get("min", 0)
    return (f"{winner} 在全部 {raroc.get('n', 0)} 个种子下 RAROC 均居首，"
            f"极差 {spread:.4f}，排序稳健")


def build_seeds(base_seed: int = 42, n: int = 3, provided: Optional[list] = None) -> list:
    if provided:
        return [int(s) for s in provided][:8]
    return [base_seed + i * 101 for i in range(max(2, min(n, 8)))]
