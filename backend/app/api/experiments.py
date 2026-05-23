"""
Experiments router: run backtests, list results, retrieve runs.
"""
from __future__ import annotations

import uuid
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ExperimentConfig, RunResult
from app.services.metrics import run_backtest
from app.data.fixtures import STRATEGIES

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

# In-memory store (no database for MVP)
_RUN_STORE: dict[str, dict] = {}


@router.post("/run", response_model=RunResult)
async def run_experiment(config: ExperimentConfig) -> RunResult:
    """
    Run a full backtest with the given configuration.
    Computes L1-L5 metrics for challenger, champion, and optional beta.
    """
    # Validate strategies exist
    for sid in [config.champion, config.challenger]:
        if sid not in STRATEGIES:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {sid}")

    if config.beta and config.beta not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Unknown beta strategy: {config.beta}")

    run_id = str(uuid.uuid4())[:12]

    result_data = run_backtest(
        champion_id=config.champion,
        challenger_id=config.challenger,
        beta_id=config.beta,
        sample_id=config.sample_id,
        slice_dim=config.slice_dim,
        slice_value=config.slice_value,
    )

    run_result = RunResult(
        run_id=run_id,
        champion=config.champion,
        challenger=config.challenger,
        beta=config.beta,
        sample_size=result_data["sample_size"],
        duration_s=result_data["duration_s"],
        snapshot_sha=result_data["snapshot_sha"],
        config=config,
        layers=result_data["layers"],
    )

    # Persist in memory
    _RUN_STORE[run_id] = run_result.model_dump()

    return run_result


@router.get("")
async def list_experiments(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List all experiment runs (most recent first)."""
    runs = list(_RUN_STORE.values())
    # Reverse for most-recent-first ordering
    runs.reverse()
    total = len(runs)
    page = runs[offset : offset + limit]

    return {
        "total": total,
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
                "summary": r["layers"].get("_summary", []),
            }
            for r in page
        ],
    }


@router.get("/history")
async def get_history() -> dict:
    """
    Return KPI trend data across all runs for dashboard charting.
    Aggregates approval_rate, bad_rate, and RAROC per strategy per run.
    """
    if not _RUN_STORE:
        return {"runs": [], "kpi_trend": []}

    trend = []
    for run_id, r in _RUN_STORE.items():
        summary = r["layers"].get("_summary", [])
        trend.append({
            "run_id": run_id,
            "snapshot_sha": r["snapshot_sha"],
            "kpis": summary,
        })

    return {"runs": len(_RUN_STORE), "kpi_trend": trend}


@router.get("/{run_id}")
async def get_experiment(run_id: str) -> dict:
    """Retrieve a specific experiment run by ID."""
    if run_id not in _RUN_STORE:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return _RUN_STORE[run_id]
