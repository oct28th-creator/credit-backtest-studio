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


def _layer_kpis(layers: dict) -> dict:
    """Per-layer KPIs only (concise context for multi-layer prompts)."""
    out = {}
    for k, v in layers.items():
        if isinstance(v, dict):
            out[k] = v.get("kpis", v.get("matrices", v))
        else:
            out[k] = v
    return out


def _base_facts(run: dict) -> dict:
    return {
        "run_id": run.get("run_id"),
        "champion": run.get("champion"),
        "challenger": run.get("challenger"),
        "beta": run.get("beta"),
        "sample_size": run.get("sample_size"),
    }


def _extract_facts_for_layer(run: dict, layer: Optional[str] = None) -> dict:
    """
    Extract facts from a run for LLM consumption.

    The run is stored frontend-shaped: layers are keyed by layer id
    (l1..l5), each holding {kpis: [{version, ...}], ...charts}. We pass the
    real metrics straight through so the model reasons over actual numbers.
    """
    layers = run.get("layers", {})
    facts = _base_facts(run)
    if layer and layer.lower() in layers:
        facts["layer"] = layer
        facts["metrics"] = layers[layer.lower()]
    else:
        # No specific layer (chat / general): pass per-layer KPIs across all layers
        facts["metrics"] = _layer_kpis(layers)
    return facts


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

    # Comprehensive facts: per-layer KPIs across all layers
    facts = _base_facts(run)
    facts["metrics"] = _layer_kpis(run.get("layers", {}))

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

    # Per-layer KPIs across all layers so the model can rank strategies
    facts = _base_facts(run)
    facts["metrics"] = _layer_kpis(run.get("layers", {}))

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
