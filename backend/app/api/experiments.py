"""
Experiments router: thin HTTP shell over the run-execution service.

The logic lives in app/core/runs.py so the agent layer can run experiments
through exactly the same path (same manifest, same lineage, same persistence).
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.schemas import (
    ExperimentConfig, SliceRequest, RunSubmit, RunAnnotation,
)
from app.ratelimit import limiter, RUN_LIMIT, RESLICE_LIMIT
from app.db import repository
from app.core import jobs
from app.core import runs as runs_service
from app.core.manifest import build_manifest
from app.core.runs import (  # re-exported: other modules import these from here
    RunNotFound, ConfigInvalid, rehydrate_run_store, _RUN_STORE,
)

logger = logging.getLogger("backtest.experiments")

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def get_run_or_404(run_id: str) -> dict:
    """HTTP-facing lookup used by this router and by the AI router."""
    try:
        return runs_service.get_run(run_id)
    except RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _validate_config(config: ExperimentConfig) -> None:
    try:
        runs_service.validate_config(config)
    except ConfigInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))


_new_run_id = runs_service.new_run_id
_execute_run = runs_service.execute_run


@router.post("/run")
@limiter.limit(RUN_LIMIT)
async def run_experiment(request: Request, config: ExperimentConfig) -> dict:
    """
    Run a full backtest synchronously and return the frontend layer structure.

    Kept for interactive use; agents and sweeps should use POST /submit.
    """
    _validate_config(config)

    from app.strategies.sandbox import StrategyExecutionError

    run_id = _new_run_id()
    try:
        return await _execute_run(run_id, config)
    except (ValueError, LookupError, StrategyExecutionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{run_id}/reslice")
@limiter.limit(RESLICE_LIMIT)
async def reslice_experiment(request: Request, run_id: str, slice_req: SliceRequest) -> dict:
    """
    Re-run a completed backtest filtered to a single dimension slice.

    The slice produces a NEW immutable run linked to the original by lineage
    (``parent_run_id`` / ``root_run_id``). The previous behaviour overwrote the
    original run, which destroyed the evidence trail — unacceptable once an
    agent cites run ids as evidence.
    """
    run = get_run_or_404(run_id)
    config = ExperimentConfig(**run["config"])
    config.slice_dim = slice_req.slice_dim
    config.slice_value = slice_req.slice_value

    child_id = _new_run_id()
    root_id = run.get("root_run_id") or run_id
    return await _execute_run(
        child_id, config,
        parent_run_id=run_id, root_run_id=root_id,
        created_by=run.get("created_by", "user"),
    )


# --------------------------------------------------------------------------- #
# Asynchronous submission — the entry point an agent uses
# --------------------------------------------------------------------------- #
@router.post("/submit", status_code=202)
@limiter.limit(RUN_LIMIT)
async def submit_experiment(request: Request, body: RunSubmit) -> dict:
    """Queue a run and return immediately with a run_id to poll.

    Also reports prior runs carrying the same manifest hash, so a caller can
    reuse an identical experiment instead of paying for it twice.
    """
    config = body.config
    _validate_config(config)

    run_id = _new_run_id()
    manifest = build_manifest(config.model_dump(), root_run_id=run_id,
                              created_by=body.created_by)
    prior = repository.find_runs_by_manifest(manifest["manifest_sha"])

    jobs.create(run_id, manifest["manifest_sha"], body.created_by)
    try:
        repository.create_run(
            run_id, config.model_dump(), {}, "", manifest=manifest,
            root_run_id=run_id, status=jobs.QUEUED, created_by=body.created_by,
            hypothesis=body.hypothesis, tags=body.tags,
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to persist queued run %s", run_id)

    async def _job() -> dict:
        result = await _execute_run(
            run_id, config, root_run_id=run_id, created_by=body.created_by,
            hypothesis=body.hypothesis, tags=body.tags,
        )
        return result

    jobs.launch(run_id, _job)

    return {
        "run_id": run_id,
        "status": jobs.QUEUED,
        "manifest_sha": manifest["manifest_sha"],
        "identical_prior_runs": prior,
    }


@router.get("/jobs")
async def list_jobs(limit: int = Query(default=50, ge=1, le=200),
                    status: Optional[str] = Query(default=None)) -> dict:
    """Lifecycle view over recent runs (queued/running/succeeded/failed)."""
    return {"jobs": jobs.list_jobs(limit=limit, status=status)}


@router.get("/{run_id}/status")
async def get_run_status(run_id: str) -> dict:
    job = jobs.get(run_id)
    if job is not None:
        return job.to_dict()
    stored = repository.get_run(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return {
        "run_id": run_id,
        "status": stored.get("status") or "succeeded",
        "manifest_sha": stored.get("manifest_sha"),
        "created_by": stored.get("created_by"),
        "result_available": bool(stored.get("result")),
    }


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    cancelled = jobs.cancel(run_id)
    if cancelled:
        repository.update_run_status(run_id, jobs.CANCELLED)
    return {"run_id": run_id, "cancelled": cancelled}


@router.get("/{run_id}/guardrails")
async def get_run_guardrails(run_id: str) -> dict:
    """Deterministic trust checks for one run — the same ones the agent's
    Critic is bound by, so a person reading the results sees the same
    caveats the machine does."""
    from app.agent import guardrails

    return guardrails.check_run(get_run_or_404(run_id))


@router.get("/{run_id}/decomposition")
async def get_run_decomposition(run_id: str, strategy: Optional[str] = None) -> dict:
    """Where the challenger's gain came from — model discrimination or a
    loosened policy gate. Computed from the attribution table."""
    from app.agent import insights

    run = get_run_or_404(run_id)
    sid = strategy or run.get("challenger")
    matrix = (run.get("layers", {}).get("l4", {}).get("matrices", {}) or {}).get(sid)
    out = insights.decompose_swap(matrix) if matrix else None
    if out is None:
        raise HTTPException(status_code=404, detail=f"no swap-set attribution for {sid}")
    return {"run_id": run_id, "strategy": sid, **out}


@router.get("/{run_id}/bundle")
@limiter.limit(RUN_LIMIT)
async def get_evidence_bundle(request: Request, run_id: str,
                              replication: bool = Query(default=False)) -> dict:
    """The approval pack. ``replication=true`` spends compute on a 3-seed
    rerun; without it the pack says so under 'what this does not answer'."""
    from app.agent import tools as agent_tools

    get_run_or_404(run_id)
    try:
        return await agent_tools.build_evidence_bundle(
            run_id, include_replication=replication, include_ri_comparison=True)
    except agent_tools.ToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{run_id}/manifest")
async def get_run_manifest(run_id: str) -> dict:
    """The reproducibility document: same manifest_sha => same numbers."""
    stored = repository.get_run(run_id)
    if stored is None or not stored.get("manifest"):
        raise HTTPException(status_code=404, detail=f"No manifest for run: {run_id}")
    return stored["manifest"]


@router.get("/{run_id}/lineage")
async def get_run_lineage(run_id: str) -> dict:
    """Every run derived from the same root — one experiment thread."""
    stored = repository.get_run(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    root = stored.get("root_run_id") or run_id
    return {"root_run_id": root, "runs": repository.get_lineage(root)}


@router.post("/{run_id}/annotate")
async def annotate_run(run_id: str, body: RunAnnotation) -> dict:
    """Record the question and the finding alongside the metrics.

    This is what turns a pile of runs into a searchable experiment registry —
    the memory an agent reads before proposing the next experiment.
    """
    if repository.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    ok = repository.annotate_run(run_id, body.hypothesis, body.conclusion, body.tags)
    if not ok:
        raise HTTPException(status_code=400, detail="nothing to annotate")
    stored = repository.get_run(run_id)
    return {
        "run_id": run_id,
        "hypothesis": stored.get("hypothesis"),
        "conclusion": stored.get("conclusion"),
        "tags": stored.get("tags", []),
    }


@router.get("")
async def list_experiments(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    # Only completed runs carry layer metrics; a queued/failed job is visible
    # through /jobs and /{run_id}/status instead.
    runs = [r for r in reversed(list(_RUN_STORE.values())) if r.get("layers")]
    return {
        "total": len(runs),
        "offset": offset,
        "limit": limit,
        "runs": [
            {
                "run_id": r["run_id"],
                "champion": r["champion"],
                "challenger": r["challenger"],
                "beta": r["beta"],
                "sample_size": r["sample_size"],
                "duration_s": r["duration_s"],
                "snapshot_sha": r["snapshot_sha"],
            }
            for r in runs[offset: offset + limit]
        ],
    }


@router.get("/history")
async def get_history() -> dict:
    if not _RUN_STORE:
        return {"runs": [], "kpi_trend": []}

    trend = []
    for run_id, r in _RUN_STORE.items():
        if not r.get("layers"):
            continue
        l2_kpis = r.get("layers", {}).get("l2", {}).get("kpis", [])
        trend.append({
            "run_id": run_id,
            "snapshot_sha": r["snapshot_sha"],
            "kpis": l2_kpis,
        })

    return {"runs": len(_RUN_STORE), "kpi_trend": trend}


@router.get("/{run_id}")
async def get_experiment(run_id: str) -> dict:
    return get_run_or_404(run_id)
