"""Agent router: the tool surface, session budgets, and the investigation loop.

Two ways in:
  - call tools directly (an external agent, a script, the future MCP server)
  - stream a full investigation and watch each phase land
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent import budget as budget_mod
from app.agent import orchestrator, tools
from app.core.runs import RunNotFound, ConfigInvalid
from app.models.schemas import Language
from app.ratelimit import limiter, AGENT_LIMIT, RUN_LIMIT

logger = logging.getLogger("backtest.agent.api")

router = APIRouter(prefix="/api/agent", tags=["agent"])


class BudgetSpec(BaseModel):
    max_experiments: int = 12
    max_llm_calls: int = 12
    max_wall_seconds: int = 900


class SessionCreate(BaseModel):
    goal: str = Field(default="", max_length=2000)
    budget: Optional[BudgetSpec] = None


class ToolCall(BaseModel):
    args: dict = Field(default_factory=dict)
    session_id: Optional[str] = None


class InvestigateRequest(BaseModel):
    goal: str = Field(..., max_length=2000)
    base_config: dict = Field(default_factory=dict)
    language: Language = "zh"
    budget: Optional[BudgetSpec] = None
    session_id: Optional[str] = None


def _session_or_404(session_id: str) -> budget_mod.Session:
    session = budget_mod.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session


# --------------------------------------------------------------------------- #
# Tool surface
# --------------------------------------------------------------------------- #
@router.get("/tools")
async def list_tools() -> dict:
    """The complete list of things an agent may do here."""
    return {"tools": tools.describe()}


@router.post("/tools/{name}")
@limiter.limit(RUN_LIMIT)
async def call_tool(request: Request, name: str, body: ToolCall) -> dict:
    session = budget_mod.get(body.session_id) if body.session_id else None
    if body.session_id and session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {body.session_id}")
    try:
        result = await tools.call(name, body.args, session=session)
    except tools.ToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConfigInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except budget_mod.BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    return {"tool": name, "result": result,
            "session": session.to_dict() if session else None}


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate) -> dict:
    b = budget_mod.Budget(**body.budget.model_dump()) if body.budget else None
    return budget_mod.create(goal=body.goal, budget=b).to_dict()


@router.get("/sessions")
async def list_sessions(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"sessions": budget_mod.list_sessions(limit)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    return _session_or_404(session_id).to_dict()


# --------------------------------------------------------------------------- #
# Investigation loop
# --------------------------------------------------------------------------- #
@router.post("/investigate/stream")
@limiter.limit(AGENT_LIMIT)
async def investigate_stream(request: Request, body: InvestigateRequest) -> StreamingResponse:
    """Run Designer → Executor → Analyst → Critic, streaming one event per phase."""
    if body.session_id:
        session = _session_or_404(body.session_id)
    else:
        b = budget_mod.Budget(**body.budget.model_dump()) if body.budget else None
        session = budget_mod.create(goal=body.goal, budget=b)

    async def _gen():
        try:
            async for event in orchestrator.investigate(
                goal=body.goal, base_config=body.base_config,
                session=session, language=body.language,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001 — the stream reports its own failure
            logger.exception("agent investigation failed")
            payload = {"phase": "error", "error": f"{type(exc).__name__}: {exc}"}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


@router.post("/investigate")
@limiter.limit(AGENT_LIMIT)
async def investigate_sync(request: Request, body: InvestigateRequest) -> dict:
    """Same loop, collected into one response (for scripts and tests)."""
    if body.session_id:
        session = _session_or_404(body.session_id)
    else:
        b = budget_mod.Budget(**body.budget.model_dump()) if body.budget else None
        session = budget_mod.create(goal=body.goal, budget=b)

    events = []
    async for event in orchestrator.investigate(
        goal=body.goal, base_config=body.base_config,
        session=session, language=body.language,
    ):
        events.append(event)
    final = events[-1] if events else {}
    return {"session": session.to_dict(), "events": events, "result": final}
