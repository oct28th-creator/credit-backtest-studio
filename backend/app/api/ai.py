"""
AI router: SSE streaming endpoints for LLM analysis.
"""
from __future__ import annotations

import json
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models.schemas import NLParseRequest, AILayerRequest, AIChatRequest
from app.services import llm
from app.config import settings
from app.api.experiments import _RUN_STORE

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
async def ai_status() -> dict:
    """Diagnostics: is the real LLM configured? (never exposes the key)"""
    key = settings.deepseek_api_key or ""
    return {
        "llm_available": settings.llm_available,
        "model": settings.deepseek_model,
        "base_url": settings.deepseek_base_url,
        "api_key_present": bool(key),
        "api_key_hint": (key[:5] + "…" + key[-2:]) if len(key) > 8 else ("set" if key else "missing"),
    }


def _get_run(run_id: str) -> dict:
    if run_id not in _RUN_STORE:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return _RUN_STORE[run_id]


def _extract_facts_for_layer(run: dict, layer: Optional[str] = None) -> dict:
    """Extract relevant facts from a run for LLM consumption."""
    layers = run.get("layers", {})
    summary = layers.get("_summary", [])

    if layer and layer.lower() in layers.get(run["challenger"], {}):
        challenger_layer = layers.get(run["challenger"], {}).get(layer.lower(), {})
        champion_layer = layers.get(run["champion"], {}).get(layer.lower(), {})
        beta = run.get("beta")
        beta_layer = layers.get(beta, {}).get(layer.lower(), {}) if beta else {}

        return {
            "run_id": run["run_id"],
            "layer": layer,
            "challenger": {run["challenger"]: challenger_layer},
            "champion": {run["champion"]: champion_layer},
            "beta": {beta: beta_layer} if beta else {},
            "summary": summary,
        }

    # Return full summary facts if no specific layer
    return {
        "run_id": run["run_id"],
        "sample_size": run["sample_size"],
        "strategies": {
            run["champion"]: _safe_layer_summary(layers.get(run["champion"], {})),
            run["challenger"]: _safe_layer_summary(layers.get(run["challenger"], {})),
        },
        "summary": summary,
    }


def _safe_layer_summary(strategy_layers: dict) -> dict:
    """Extract key KPIs from strategy layers for concise LLM context."""
    return {
        "l1": {
            "auc": strategy_layers.get("l1", {}).get("auc"),
            "ks": strategy_layers.get("l1", {}).get("ks"),
            "lift_at_20": strategy_layers.get("l1", {}).get("lift_at_20"),
            "brier_score": strategy_layers.get("l1", {}).get("brier_score"),
        },
        "l2": {
            "approval_rate": strategy_layers.get("l2", {}).get("approval_rate"),
            "bad_rate": strategy_layers.get("l2", {}).get("bad_rate"),
            "raroc": strategy_layers.get("l2", {}).get("raroc"),
            "avg_profit_per_approved": strategy_layers.get("l2", {}).get("avg_profit_per_approved"),
        },
        "l3": {
            "mob12_bad_rate": strategy_layers.get("l3", {}).get("mob12_bad_rate"),
            "fpd_rate": strategy_layers.get("l3", {}).get("fpd_rate"),
            "roll_rates": strategy_layers.get("l3", {}).get("roll_rates"),
        },
        "l5": {
            "di_ratios": strategy_layers.get("l5", {}).get("di_ratios"),
            "has_compliance_issue": strategy_layers.get("l5", {}).get("has_compliance_issue"),
        },
    }


async def _sse_generator(gen: AsyncGenerator) -> AsyncGenerator[str, None]:
    """Wrap an async generator, ensuring proper SSE formatting."""
    async for chunk in gen:
        yield chunk


@router.post("/parse-config/stream")
async def stream_parse_config(request: NLParseRequest) -> StreamingResponse:
    """
    Parse natural language into ExperimentConfig via streaming SSE.
    """
    gen = llm.stream_parse_config(request.text, request.language)
    return StreamingResponse(
        _sse_generator(gen),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analyze-layer/stream/{run_id}")
async def stream_analyze_layer(
    run_id: str,
    layer: str = Query(default="l1", description="Layer to analyze: l1..l5"),
    language: str = Query(default="zh", description="Language: zh or en"),
) -> StreamingResponse:
    """
    Stream layer-specific analysis for a completed backtest run.
    """
    run = _get_run(run_id)
    facts = _extract_facts_for_layer(run, layer)

    gen = llm.stream_analyze_layer(run_id, layer, facts, language)
    return StreamingResponse(
        _sse_generator(gen),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/stream")
async def stream_chat(request: AIChatRequest) -> StreamingResponse:
    """
    Stream interactive chat about a backtest run.
    """
    run = _get_run(request.run_id)
    facts = _extract_facts_for_layer(run, request.layer)

    gen = llm.stream_chat(
        run_id=request.run_id,
        message=request.message,
        history=request.history,
        layer=request.layer,
        facts=facts,
        language=request.language,
    )
    return StreamingResponse(
        _sse_generator(gen),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/report/stream/{run_id}")
async def stream_report(
    run_id: str,
    language: str = Query(default="zh", description="Language: zh or en"),
) -> StreamingResponse:
    """
    Stream a full Markdown report for a backtest run.
    """
    run = _get_run(run_id)

    # Build comprehensive facts for the report
    layers = run.get("layers", {})
    facts = {
        "run_id": run_id,
        "champion": run["champion"],
        "challenger": run["challenger"],
        "beta": run.get("beta"),
        "sample_size": run["sample_size"],
        "summary": layers.get("_summary", []),
        "strategies": {
            sid: _safe_layer_summary(layers.get(sid, {}))
            for sid in [run["champion"], run["challenger"]]
            if sid in layers
        },
    }
    if run.get("beta") and run["beta"] in layers:
        facts["strategies"][run["beta"]] = _safe_layer_summary(layers[run["beta"]])

    gen = llm.stream_report(run_id, facts, language)
    return StreamingResponse(
        _sse_generator(gen),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/compare/stream")
async def stream_compare(
    run_id: str = Query(..., description="Run ID to compare strategies"),
    language: str = Query(default="zh", description="Language: zh or en"),
) -> StreamingResponse:
    """
    Stream multi-strategy comparison analysis.
    """
    run = _get_run(run_id)
    layers = run.get("layers", {})

    all_strategy_ids = [run["champion"], run["challenger"]]
    if run.get("beta"):
        all_strategy_ids.append(run["beta"])

    facts = {
        "run_id": run_id,
        "strategies": {},
        "summary": layers.get("_summary", []),
    }
    for sid in all_strategy_ids:
        if sid in layers:
            facts["strategies"][sid] = _safe_layer_summary(layers[sid])

    gen = llm.stream_compare_strategies(facts, language)
    return StreamingResponse(
        _sse_generator(gen),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
