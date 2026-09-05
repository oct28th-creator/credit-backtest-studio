"""Experiment history: the thread view, not the log view.

The old history page was a flat list of runs sorted by time, which is how a
tool that ships one experiment at a time thinks. A platform where reslicing,
repairing and replicating all mint new runs produces *threads*: one question,
several attempts, one verdict. So history is served three ways here —

  GET /api/history        flat list, with each run's guardrail verdict
  GET /api/history/trees  the same runs grouped into experiment threads
  GET /api/history/diff   two runs aligned metric by metric, L1–L5

The verdict on every row is the same deterministic guardrail check that binds
the agent's Critic. A run that a person cannot ship should not look identical
in the list to one they can.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.agent import guardrails
from app.core import runs as runs_service
from app.db import repository

router = APIRouter(prefix="/api/history", tags=["history"])


# --------------------------------------------------------------------------- #
# Metric dictionary — what "compare two runs" means, spelled out once
# --------------------------------------------------------------------------- #
# (layer, key, label_zh, label_en, format, higher_is_better | None for neutral)
_DIFF_METRICS: list[tuple] = [
    ("l1", "ks",             "KS",             "KS",             "num3",  True),
    ("l1", "auc",            "AUC",            "AUC",            "num3",  True),
    ("l1", "lift20",         "Lift@20%",       "Lift@20%",       "num2",  True),
    ("l1", "brier",          "Brier",          "Brier",          "num4",  False),
    ("l2", "approval_rate",  "通过率",          "Approval rate",  "pct",   None),
    ("l2", "el",             "坏账率",          "Bad rate",       "pct2",  False),
    ("l2", "raroc",          "RAROC",          "RAROC",          "pct",   True),
    ("l2", "avg_profit",     "户均利润",        "Profit / account", "money", True),
    ("l2", "n_approved",     "核准户数",        "Approved accounts", "int", None),
    ("l3", "m12_bad",        "MOB12 坏账",      "MOB12 bad",      "pct2",  False),
    ("l3", "fpd",            "首逾 FPD",        "FPD",            "pct2",  False),
    ("l3", "m1_m2_roll",     "M1→M2 迁徙",      "M1→M2 roll",     "pct2",  False),
    ("l5", "di_min",         "最低 DI 比率",     "Lowest DI ratio", "num3", True),
]

_CONFIG_FIELDS = [
    ("champion", "冠军策略", "Champion"),
    ("challenger", "挑战者", "Challenger"),
    ("beta", "对照 β", "Beta"),
    ("sample_id", "样本", "Sample"),
    ("sample_size", "实际评估行数", "Rows evaluated"),
    ("seed", "随机种子", "Seed"),
    ("slice_dim", "切片维度", "Slice dimension"),
    ("slice_value", "切片取值", "Slice value"),
    ("reject_inference", "拒绝推断", "Reject inference"),
]


def _kpi(layer: dict, version: str) -> dict:
    for k in layer.get("kpis", []) or []:
        if k.get("version") == version:
            return k
    return {}


def _di_min(run: dict, version: str) -> Optional[float]:
    di = ((run.get("layers", {}) or {}).get("l5", {}).get("di_by_group", {}) or {}).get(version)
    if not di:
        return None
    vals = [v for v in di.values() if isinstance(v, (int, float))]
    return min(vals) if vals else None


def _metric(run: dict, version: str, layer: str, key: str):
    if key == "di_min":
        return _di_min(run, version)
    layers = run.get("layers", {}) or {}
    return _kpi(layers.get(layer, {}) or {}, version).get(key)


def _verdict(run: dict) -> dict:
    """Deterministic, cheap: reads the layers already in memory."""
    try:
        report = guardrails.check_run(run)
    except Exception:  # noqa: BLE001 — a malformed old run must not break the list
        return {"verdict": "unknown", "blocking": [], "warnings": []}
    blocking = [f["code"] for f in report.get("blocking", [])]
    warnings = [f["code"] for f in report.get("warnings", [])]
    return {
        "verdict": "blocked" if blocking else "warned" if warnings else "clean",
        "blocking": blocking,
        "warnings": warnings,
    }


def _summary(run: dict, row: Optional[dict]) -> dict:
    """One row of history: what it was, what came out, whether it can ship."""
    config = run.get("config", {}) or {}
    challenger = run.get("challenger")
    l1 = _kpi((run.get("layers", {}) or {}).get("l1", {}) or {}, challenger)
    l2 = _kpi((run.get("layers", {}) or {}).get("l2", {}) or {}, challenger)
    item = {
        "run_id": run.get("run_id"),
        "timestamp": (row or {}).get("created_at") or "",
        "champion": run.get("champion"),
        "challenger": challenger,
        "beta": run.get("beta"),
        "sample_id": config.get("sample_id") or "",
        "sample_size": run.get("sample_size"),
        "duration_s": run.get("duration_s") or 0.0,
        "l1_ks": l1.get("ks") or 0.0,
        "l1_auc": l1.get("auc") or 0.0,
        "l2_raroc": l2.get("raroc") or 0.0,
        "l2_approval_rate": l2.get("approval_rate"),
        "l2_bad_rate": l2.get("el"),
        "manifest_sha": run.get("manifest_sha"),
        "parent_run_id": run.get("parent_run_id"),
        "root_run_id": run.get("root_run_id") or run.get("run_id"),
        "created_by": run.get("created_by") or (row or {}).get("created_by") or "user",
        "slice": {"dim": config.get("slice_dim"), "value": config.get("slice_value")},
        "overrides": config.get("policy_overrides") or {},
        "environment": ((run.get("environment") or {}).get("id")),
        "hypothesis": (row or {}).get("hypothesis"),
        "conclusion": (row or {}).get("conclusion"),
        "tags": (row or {}).get("tags") or [],
    }
    item.update(_verdict(run))
    return item


def _rows_by_id() -> dict[str, dict]:
    """created_at / annotations live in SQLite; metrics live in the run store."""
    out: dict[str, dict] = {}
    try:
        for r in repository.search_runs(limit=500):
            out[r["run_id"]] = r
    except Exception:  # noqa: BLE001 — history still works without the registry
        pass
    return out


def _all_summaries() -> list[dict]:
    rows = _rows_by_id()
    items = [
        _summary(run, rows.get(run_id))
        for run_id, run in runs_service._RUN_STORE.items()
        if run.get("layers")
    ]
    # Newest first, falling back to insertion order when created_at is missing.
    items.reverse()
    items.sort(key=lambda i: i["timestamp"] or "", reverse=True)
    return items


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("")
async def list_history(
    strategy: Optional[str] = None,
    sample: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[dict]:
    """Flat list, newest first. Returns [] when nothing has been run yet —
    an empty history is a fact about this install, not a reason to show
    fixture data."""
    items = _all_summaries()
    if strategy:
        items = [i for i in items if strategy in (i["champion"], i["challenger"], i["beta"])]
    if sample:
        items = [i for i in items if i["sample_id"] == sample]
    return items[:limit]


@router.get("/trees")
async def list_trees(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """Runs grouped into experiment threads.

    A thread is every run sharing a root: the first submission, its reslices,
    the repair attempts, the replications. Depth is the parent chain, so the
    UI can indent instead of asking the reader to match run_id prefixes.
    """
    items = _all_summaries()
    by_id = {i["run_id"]: i for i in items}

    def depth(item: dict, seen: Optional[set] = None) -> int:
        seen = seen or set()
        pid = item.get("parent_run_id")
        if not pid or pid in seen or pid not in by_id:
            return 0
        seen.add(pid)
        return 1 + depth(by_id[pid], seen)

    trees: dict[str, dict] = {}
    for item in items:
        root = item["root_run_id"] or item["run_id"]
        node = {**item, "depth": depth(item)}
        tree = trees.setdefault(root, {"root_run_id": root, "nodes": []})
        tree["nodes"].append(node)

    out = []
    for tree in trees.values():
        # Oldest first inside a thread: a thread reads forward in time.
        tree["nodes"].sort(key=lambda n: n["timestamp"] or "")
        first = tree["nodes"][0]
        blocked = sum(1 for n in tree["nodes"] if n["verdict"] == "blocked")
        clean = sum(1 for n in tree["nodes"] if n["verdict"] == "clean")
        tree.update({
            "started_at": first["timestamp"],
            "last_at": tree["nodes"][-1]["timestamp"],
            "n_runs": len(tree["nodes"]),
            "n_blocked": blocked,
            "n_clean": clean,
            "question": next((n["hypothesis"] for n in tree["nodes"] if n["hypothesis"]), None),
            "finding": next((n["conclusion"] for n in reversed(tree["nodes"]) if n["conclusion"]), None),
            "champion": first["champion"],
            "challenger": first["challenger"],
            "sample_id": first["sample_id"],
        })
        out.append(tree)
    out.sort(key=lambda t: t["last_at"] or "", reverse=True)
    return {"total": len(out), "trees": out[:limit]}


@router.get("/diff")
async def diff_runs(a: str, b: str) -> dict:
    """Two runs, aligned by strategy role, metric by metric.

    Aligning by role rather than by strategy id is deliberate: comparing run A's
    challenger with run B's *champion* because they happen to share a version
    string is how a reader concludes the opposite of the truth.
    """
    try:
        run_a = runs_service.get_run(a)
        run_b = runs_service.get_run(b)
    except runs_service.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    rows_meta = _rows_by_id()
    sum_a, sum_b = _summary(run_a, rows_meta.get(a)), _summary(run_b, rows_meta.get(b))

    config_diff = []
    ca, cb = run_a.get("config", {}) or {}, run_b.get("config", {}) or {}
    for key, zh, en in _CONFIG_FIELDS:
        va = run_a.get(key) if key in ("champion", "challenger", "beta", "sample_size") else ca.get(key)
        vb = run_b.get(key) if key in ("champion", "challenger", "beta", "sample_size") else cb.get(key)
        if va != vb:
            config_diff.append({"field": key, "label_zh": zh, "label_en": en, "a": va, "b": vb})
    if (ca.get("policy_overrides") or {}) != (cb.get("policy_overrides") or {}):
        config_diff.append({
            "field": "policy_overrides", "label_zh": "策略参数覆写", "label_en": "Policy overrides",
            "a": ca.get("policy_overrides") or {}, "b": cb.get("policy_overrides") or {},
        })

    roles = ["champion", "challenger", "beta"]
    metrics = []
    for role in roles:
        va, vb = run_a.get(role), run_b.get(role)
        if not va or not vb:
            continue
        for layer, key, zh, en, fmt, higher in _DIFF_METRICS:
            x, y = _metric(run_a, va, layer, key), _metric(run_b, vb, layer, key)
            if x is None and y is None:
                continue
            delta = (y - x) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None
            better = None
            if delta is not None and higher is not None and abs(delta) > 1e-9:
                better = "b" if ((delta > 0) == higher) else "a"
            metrics.append({
                "layer": layer, "key": key, "role": role,
                "strategy_a": va, "strategy_b": vb,
                "label_zh": zh, "label_en": en, "format": fmt,
                "a": x, "b": y, "delta": delta, "better": better,
            })

    same_manifest = bool(sum_a["manifest_sha"]) and sum_a["manifest_sha"] == sum_b["manifest_sha"]
    return {
        "a": sum_a,
        "b": sum_b,
        "same_manifest": same_manifest,
        # Identical manifests mean identical inputs; any metric difference then
        # would be a bug in the engine, not a finding about the strategies.
        "note_zh": ("两次运行的 manifest 完全相同，输入一致，指标差异应为零。"
                    if same_manifest else
                    "两次运行的输入不同，先看下方「配置差异」再解读指标差异。"),
        "note_en": ("Identical manifests: same inputs, so any metric difference is an engine bug."
                    if same_manifest else
                    "Inputs differ — read the config diff below before reading the metric deltas."),
        "config_diff": config_diff,
        "metrics": metrics,
    }
