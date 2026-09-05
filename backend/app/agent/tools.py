"""The agent's capability surface.

Every tool here is deterministic: no LLM, no hidden state, same inputs give
the same outputs. That is the point — the reasoning lives in the orchestrator
(or in an external agent), and everything it is *able* to do is enumerated,
schema-checked and charged to a budget here.

The registry doubles as the contract an external agent (MCP, Claude Code)
would bind to, so `describe()` returns JSON-Schema-shaped definitions.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from app.agent import budget as budget_mod
from app.agent import guardrails
from app.core import runs as runs_service
from app.core.manifest import build_manifest
from app.db import repository
from app.models.schemas import ExperimentConfig

# Bounded fan-out: the metric layer is CPU-heavy and runs in a thread pool.
_MAX_CONCURRENCY = 2


class ToolError(Exception):
    """A tool was called with arguments it cannot honour."""


# --------------------------------------------------------------------------- #
# Compact metric extraction — agents must read numbers, not chart payloads
# --------------------------------------------------------------------------- #
def _kpi(layer: dict, version: str) -> dict:
    for k in layer.get("kpis", []) or []:
        if k.get("version") == version:
            return k
    return {}


def _compact(run: dict) -> dict:
    """Strip a run down to decision-relevant numbers.

    A full run result is ~200 KB of chart series. Feeding that to a model is
    both expensive and a reliable way to get hallucinated precision, so every
    agent-facing path goes through this.
    """
    layers = run.get("layers", {}) or {}
    versions = [v for v in [run.get("champion"), run.get("challenger"), run.get("beta")] if v]
    strategies = {}
    for v in versions:
        l1, l2, l3 = _kpi(layers.get("l1", {}), v), _kpi(layers.get("l2", {}), v), _kpi(layers.get("l3", {}), v)
        di = (layers.get("l5", {}).get("di_by_group", {}) or {}).get(v, {})
        swap = (layers.get("l4", {}).get("matrices", {}) or {}).get(v, {})
        strategies[v] = {
            "role": ("champion" if v == run.get("champion")
                     else "challenger" if v == run.get("challenger") else "beta"),
            "approval_rate": l2.get("approval_rate"),
            "bad_rate": l2.get("el"),
            "raroc": l2.get("raroc"),
            "avg_profit": l2.get("avg_profit"),
            "ks": l1.get("ks"),
            "auc": l1.get("auc"),
            "mob12_bad": l3.get("m12_bad"),
            "fpd": l3.get("fpd"),
            "di": di or None,
            "swap_vs_champion": {
                "swap_in": (swap.get("swap_in") or {}).get("count"),
                "swap_out": (swap.get("swap_out") or {}).get("count"),
                "swap_in_bad_rate": (swap.get("swap_in") or {}).get("bad_rate"),
                "swap_out_bad_rate": (swap.get("swap_out") or {}).get("bad_rate"),
                "p_value": swap.get("p_value"),
            } if swap else None,
        }
    config = run.get("config", {}) or {}
    return {
        "run_id": run.get("run_id"),
        "manifest_sha": run.get("manifest_sha"),
        "sample_size": run.get("sample_size"),
        "seed": config.get("seed"),
        "slice": {"dim": config.get("slice_dim"), "value": config.get("slice_value")},
        "policy_overrides": config.get("policy_overrides") or {},
        "strategies": strategies,
    }


def _merge_config(base: dict, patch: Optional[dict]) -> ExperimentConfig:
    merged = {**(base or {}), **(patch or {})}
    # policy_overrides merge per strategy instead of wholesale replacement
    base_ov = (base or {}).get("policy_overrides") or {}
    patch_ov = (patch or {}).get("policy_overrides") or {}
    if base_ov or patch_ov:
        merged["policy_overrides"] = {
            k: {**base_ov.get(k, {}), **patch_ov.get(k, {})}
            for k in set(base_ov) | set(patch_ov)
        }
    try:
        return ExperimentConfig(**merged)
    except Exception as exc:  # noqa: BLE001 — pydantic error surfaces as a tool error
        raise ToolError(f"invalid experiment config: {exc}") from exc


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
async def list_strategies() -> dict:
    from app.data.fixtures import STRATEGIES

    builtin = [{"ref": f"builtin:{k}", "id": k, "name": v.get("name"),
                "role": v.get("role"), "desc": v.get("desc_zh"),
                "knobs": sorted(_OVERRIDABLE())}
               for k, v in STRATEGIES.items()]
    custom = [{"ref": f"custom:{s['id']}", "id": s["id"], "name": s.get("name"),
               "role": s.get("role"), "version": s.get("version")}
              for s in repository.list_custom_strategies()]
    return {"builtin": builtin, "custom": custom}


def _OVERRIDABLE() -> set:
    from app.data.fixtures import _OVERRIDABLE_POLICY

    return _OVERRIDABLE_POLICY


async def list_datasets() -> dict:
    from app.data.fixtures import SAMPLES

    return {
        "builtin": [{"ref": f"builtin:{s['id']}", **s} for s in SAMPLES],
        "custom": [{"ref": f"custom:{d['id']}", "id": d["id"], "name": d.get("name"),
                    "n_rows": d.get("n_rows")}
                   for d in repository.list_custom_datasets()],
    }


async def submit_experiment(
    config: dict,
    hypothesis: Optional[str] = None,
    tags: Optional[list] = None,
    created_by: str = "agent",
    reuse_identical: bool = True,
    session: Optional[budget_mod.Session] = None,
) -> dict:
    """Run one experiment. Reuses an identical prior run when one exists."""
    cfg = _merge_config(config, None)
    runs_service.validate_config(cfg)

    manifest = build_manifest(cfg.model_dump(), created_by=created_by)
    if reuse_identical:
        prior = repository.find_runs_by_manifest(manifest["manifest_sha"], limit=1)
        if prior:
            run_id = prior[0]["run_id"]
            if session:
                session.record_run(run_id, cached=True)
            # A cached hit must answer the same question a fresh run does,
            # otherwise the agent re-runs it just to see the numbers.
            return {"run_id": run_id, "cached": True,
                    "manifest_sha": manifest["manifest_sha"],
                    "metrics": _compact(runs_service.get_run(run_id)),
                    "note": "identical manifest already run; result reused"}

    if session:
        session.spend_experiment()

    run_id = runs_service.new_run_id()
    result = await runs_service.execute_run(
        run_id, cfg, created_by=created_by, hypothesis=hypothesis, tags=tags,
    )
    if session:
        session.record_run(run_id)
    return {"run_id": run_id, "cached": False,
            "manifest_sha": result.get("manifest_sha"),
            "metrics": _compact(result)}


async def sensitivity_scan(
    base_config: dict,
    strategy: str,
    knob: str,
    values: list,
    created_by: str = "agent",
    session: Optional[budget_mod.Session] = None,
) -> dict:
    """Sweep one policy knob across values — server-side expansion.

    Expanding here rather than making the agent call submit_experiment N times
    keeps the fan-out bounded, the budget check atomic, and the resulting runs
    tagged as one sweep.
    """
    if not values:
        raise ToolError("values must be a non-empty list")
    if len(values) > 12:
        raise ToolError(f"sweep too wide: {len(values)} points (max 12)")
    if knob not in _OVERRIDABLE():
        raise ToolError(f"knob '{knob}' is not overridable; allowed: {sorted(_OVERRIDABLE())}")

    if session:
        session.spend_experiment(len(values))

    async def _one(value) -> dict:
        cfg = _merge_config(base_config, {"policy_overrides": {strategy: {knob: value}}})
        runs_service.validate_config(cfg)
        manifest = build_manifest(cfg.model_dump(), created_by=created_by)
        prior = repository.find_runs_by_manifest(manifest["manifest_sha"], limit=1)
        if prior:
            run = runs_service.get_run(prior[0]["run_id"])
            if session:
                session.record_run(run["run_id"], cached=True)
            return {"value": value, "run_id": run["run_id"], "cached": True,
                    "metrics": _compact(run)}
        run_id = runs_service.new_run_id()
        result = await runs_service.execute_run(
            run_id, cfg, created_by=created_by,
            hypothesis=f"sensitivity: {strategy}.{knob}={value}",
            tags=["sweep", f"{strategy}:{knob}"],
        )
        if session:
            session.record_run(run_id)
        return {"value": value, "run_id": run_id, "cached": False,
                "metrics": _compact(result)}

    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _guarded(v):
        async with sem:
            return await _one(v)

    points = await asyncio.gather(*[_guarded(v) for v in values])
    return {"strategy": strategy, "knob": knob, "points": list(points)}


async def get_metrics(run_id: str, layer: Optional[str] = None) -> dict:
    run = runs_service.get_run(run_id)
    if layer:
        layers = run.get("layers", {})
        if layer not in layers:
            raise ToolError(f"unknown layer: {layer}")
        return {"run_id": run_id, "layer": layer, "metrics": layers[layer].get("kpis", layers[layer])}
    return _compact(run)


async def compare_runs(run_ids: list, metrics: Optional[list] = None) -> dict:
    """Align several runs into one table an agent (or a human) can read."""
    if not run_ids:
        raise ToolError("run_ids must be a non-empty list")
    wanted = metrics or ["approval_rate", "bad_rate", "raroc", "ks", "auc", "mob12_bad"]
    rows = []
    for rid in run_ids[:24]:
        compact = _compact(runs_service.get_run(rid))
        for sid, s in compact["strategies"].items():
            rows.append({
                "run_id": rid,
                "strategy": sid,
                "role": s.get("role"),
                "sample_size": compact["sample_size"],
                "seed": compact["seed"],
                "slice": compact["slice"],
                "overrides": (compact["policy_overrides"] or {}).get(sid, {}),
                **{m: s.get(m) for m in wanted},
            })
    return {"metrics": wanted, "rows": rows}


async def get_run_status(run_id: str) -> dict:
    from app.core import jobs

    job = jobs.get(run_id)
    if job is not None:
        return job.to_dict()
    stored = repository.get_run(run_id)
    if stored is None:
        raise ToolError(f"run not found: {run_id}")
    return {"run_id": run_id, "status": stored.get("status") or "succeeded"}


async def search_experiments(query: Optional[str] = None, tag: Optional[str] = None,
                             limit: int = 20) -> dict:
    """Look for prior work before spending compute on a repeat."""
    return {"runs": repository.search_runs(query=query, tag=tag, limit=min(limit, 50))}


async def annotate_run(run_id: str, conclusion: Optional[str] = None,
                       hypothesis: Optional[str] = None,
                       tags: Optional[list] = None) -> dict:
    if repository.get_run(run_id) is None:
        raise ToolError(f"run not found: {run_id}")
    repository.annotate_run(run_id, hypothesis=hypothesis, conclusion=conclusion, tags=tags)
    stored = repository.get_run(run_id)
    return {"run_id": run_id, "hypothesis": stored.get("hypothesis"),
            "conclusion": stored.get("conclusion"), "tags": stored.get("tags", [])}


async def check_guardrails(run_id: str, thresholds: Optional[dict] = None) -> dict:
    return guardrails.check_run(runs_service.get_run(run_id), thresholds)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
_S = {"type": "string"}
_N = {"type": "number"}


class Tool:
    def __init__(self, name: str, fn: Callable, description: str,
                 params: dict, required: Optional[list] = None,
                 spends_compute: bool = False, takes_session: bool = False):
        self.name = name
        self.fn = fn
        self.description = description
        self.params = params
        self.required = required or []
        self.spends_compute = spends_compute
        self.takes_session = takes_session

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "spends_compute": self.spends_compute,
            "input_schema": {
                "type": "object",
                "properties": self.params,
                "required": self.required,
            },
        }


REGISTRY: dict[str, Tool] = {t.name: t for t in [
    Tool("list_strategies", list_strategies,
         "List built-in and uploaded strategies with their overridable knobs.", {}),
    Tool("list_datasets", list_datasets,
         "List built-in samples and uploaded datasets.", {}),
    Tool("submit_experiment", submit_experiment,
         "Run one backtest. Returns compact metrics. Reuses an identical prior run.",
         {"config": {"type": "object", "description": "ExperimentConfig fields"},
          "hypothesis": _S, "tags": {"type": "array", "items": _S},
          "reuse_identical": {"type": "boolean"}},
         required=["config"], spends_compute=True, takes_session=True),
    Tool("sensitivity_scan", sensitivity_scan,
         "Sweep one policy knob across values in a single call; returns one point per value.",
         {"base_config": {"type": "object"}, "strategy": _S, "knob": _S,
          "values": {"type": "array", "items": _N}},
         required=["base_config", "strategy", "knob", "values"],
         spends_compute=True, takes_session=True),
    Tool("get_metrics", get_metrics,
         "Compact decision-relevant metrics for one run (optionally one layer).",
         {"run_id": _S, "layer": {**_S, "enum": ["l1", "l2", "l3", "l4", "l5"]}},
         required=["run_id"]),
    Tool("compare_runs", compare_runs,
         "Align several runs into one comparison table.",
         {"run_ids": {"type": "array", "items": _S},
          "metrics": {"type": "array", "items": _S}},
         required=["run_ids"]),
    Tool("get_run_status", get_run_status, "Lifecycle status of one run.",
         {"run_id": _S}, required=["run_id"]),
    Tool("search_experiments", search_experiments,
         "Search prior runs by hypothesis/conclusion text or tag. Call before spending compute.",
         {"query": _S, "tag": _S, "limit": {"type": "integer"}}),
    Tool("annotate_run", annotate_run,
         "Attach the question and the finding to a run.",
         {"run_id": _S, "conclusion": _S, "hypothesis": _S,
          "tags": {"type": "array", "items": _S}}, required=["run_id"]),
    Tool("check_guardrails", check_guardrails,
         "Deterministic fairness/significance/sample checks on a run.",
         {"run_id": _S, "thresholds": {"type": "object"}}, required=["run_id"]),
]}


def describe() -> list[dict]:
    return [t.schema() for t in REGISTRY.values()]


async def call(name: str, args: Optional[dict] = None,
               session: Optional[budget_mod.Session] = None) -> Any:
    tool = REGISTRY.get(name)
    if tool is None:
        raise ToolError(f"unknown tool: {name}; available: {sorted(REGISTRY)}")
    kwargs = dict(args or {})
    unknown = set(kwargs) - set(tool.params)
    if unknown:
        raise ToolError(f"unknown arguments for {name}: {sorted(unknown)}")
    missing = [r for r in tool.required if r not in kwargs]
    if missing:
        raise ToolError(f"missing required arguments for {name}: {missing}")
    if tool.takes_session:
        kwargs["session"] = session
    return await tool.fn(**kwargs)
