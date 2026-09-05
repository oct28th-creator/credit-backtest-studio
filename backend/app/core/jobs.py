"""Run lifecycle registry.

A backtest used to be a request/response: the caller waited, got numbers, and
nothing about the run was observable while it happened. An agent fires many
runs and needs to poll, retry and cancel, so a run now has a state machine:

    queued -> running -> succeeded
                      -> failed
                      -> cancelled

The registry is in-process (single-node deployment today). Everything it
holds is also persisted to SQLite by the API layer, so a restart loses only
in-flight jobs — which are exactly the ones that must be re-run anyway.
Swapping this for Redis/Celery later means reimplementing this interface, not
touching callers.
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from typing import Any, Awaitable, Callable, Optional

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL = {SUCCEEDED, FAILED, CANCELLED}

_MAX_JOBS = 500


@dataclass
class Job:
    run_id: str
    status: str = QUEUED
    manifest_sha: str = ""
    created_by: str = "user"
    submitted_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    result_available: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_s"] = (
            round((self.finished_at or time.time()) - self.started_at, 3)
            if self.started_at else None
        )
        return d


_JOBS: "OrderedDict[str, Job]" = OrderedDict()
_TASKS: dict[str, asyncio.Task] = {}


def _evict() -> None:
    while len(_JOBS) > _MAX_JOBS:
        run_id, _ = _JOBS.popitem(last=False)
        _TASKS.pop(run_id, None)


def create(run_id: str, manifest_sha: str = "", created_by: str = "user") -> Job:
    job = Job(run_id=run_id, manifest_sha=manifest_sha, created_by=created_by)
    _JOBS[run_id] = job
    _evict()
    return job


def get(run_id: str) -> Optional[Job]:
    return _JOBS.get(run_id)


def list_jobs(limit: int = 50, status: Optional[str] = None) -> list[dict]:
    jobs = list(reversed(_JOBS.values()))
    if status:
        jobs = [j for j in jobs if j.status == status]
    return [j.to_dict() for j in jobs[:limit]]


def mark(run_id: str, status: str, error: Optional[str] = None,
         result_available: Optional[bool] = None) -> Optional[Job]:
    job = _JOBS.get(run_id)
    if job is None:
        return None
    job.status = status
    if status == RUNNING and job.started_at is None:
        job.started_at = time.time()
    if status in TERMINAL:
        job.finished_at = time.time()
    if error is not None:
        job.error = error
    if result_available is not None:
        job.result_available = result_available
    return job


def launch(run_id: str, coro_factory: Callable[[], Awaitable[Any]]) -> asyncio.Task:
    """Run ``coro_factory()`` in the background, tracking its lifecycle."""

    async def _wrapper() -> None:
        mark(run_id, RUNNING)
        try:
            await coro_factory()
        except asyncio.CancelledError:
            mark(run_id, CANCELLED, error="cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 — the job status is the report
            mark(run_id, FAILED, error=f"{type(exc).__name__}: {exc}")
        else:
            mark(run_id, SUCCEEDED, result_available=True)

    task = asyncio.create_task(_wrapper())
    _TASKS[run_id] = task
    return task


def cancel(run_id: str) -> bool:
    task = _TASKS.get(run_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def reset() -> None:
    """Test hook."""
    _JOBS.clear()
    _TASKS.clear()
