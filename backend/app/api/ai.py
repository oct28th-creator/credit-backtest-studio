"""
AI router: SSE streaming endpoints for LLM analysis.
"""

from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.models.schemas import Language, NLParseRequest, AILayerRequest, AIChatRequest
from app.services import llm
from app.config import settings
from app.data.fixtures import STRATEGIES
from app.api.experiments import get_run_or_404
from app.ratelimit import limiter, AI_LIMIT

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
async def ai_status() -> dict:
    """Diagnostics: is the real LLM configured? (never exposes the key)"""
    return {
        "llm_available": settings.llm_available,
        "model": settings.deepseek_model,
        "base_url": settings.deepseek_base_url,
        "api_key_present": bool(settings.deepseek_api_key),
    }


def _get_run(run_id: str) -> dict:
    return get_run_or_404(run_id)


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


def _trust_facts(run: dict) -> dict:
    """Environment limits + guardrail findings, so no narrative is produced
    without the caveats that bound it."""
    from app.agent import guardrails

    env = run.get("environment") or {}
    report = guardrails.check_run(run)
    return {
        "environment": {
            "id": env.get("id"), "level": env.get("level"),
            "confidence": env.get("confidence"),
            "not_valid_for": env.get("not_valid_for", []),
            "reject_inference": (env.get("reject_inference") or {}).get("max_relative_error"),
        },
        "guardrails": {
            "ok": report["ok"],
            "blocking": [f"{b['code']}: {b['detail']}" for b in report["blocking"]],
            "warnings": [f"{w['code']}: {w['detail']}" for w in report["warnings"]],
        },
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
    facts["trust"] = _trust_facts(run)
    if layer and layer.lower() in layers:
        facts["layer"] = layer
        facts["metrics"] = layers[layer.lower()]
    else:
        # No specific layer (chat / general): pass per-layer KPIs across all layers
        facts["metrics"] = _layer_kpis(layers)
    return facts


@router.post("/parse-config/stream")
@limiter.limit(AI_LIMIT)
async def stream_parse_config(request: Request, body: NLParseRequest) -> StreamingResponse:
    """
    Parse natural language into ExperimentConfig via streaming SSE.
    """
    gen = llm.stream_parse_config(body.text, body.language)
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analyze-layer/stream/{run_id}")
@limiter.limit(AI_LIMIT)
async def stream_analyze_layer(
    request: Request,
    run_id: str,
    layer: str = Query(default="l1", description="Layer to analyze: l1..l5"),
    language: Language = Query(default="zh", description="Language: zh or en"),
) -> StreamingResponse:
    """
    Stream layer-specific analysis for a completed backtest run.
    """
    run = _get_run(run_id)
    facts = _extract_facts_for_layer(run, layer)

    gen = llm.stream_analyze_layer(run_id, layer, facts, language)
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/stream")
@limiter.limit(AI_LIMIT)
async def stream_chat(request: Request, body: AIChatRequest) -> StreamingResponse:
    """
    Stream interactive chat about a backtest run.
    """
    run = _get_run(body.run_id)
    facts = _extract_facts_for_layer(run, body.layer)

    gen = llm.stream_chat(
        run_id=body.run_id,
        message=body.message,
        history=body.history,
        layer=body.layer,
        facts=facts,
        language=body.language,
    )
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/report/stream/{run_id}")
@limiter.limit(AI_LIMIT)
async def stream_report(
    request: Request,
    run_id: str,
    language: Language = Query(default="zh", description="Language: zh or en"),
) -> StreamingResponse:
    """
    Stream a full Markdown report for a backtest run.
    """
    run = _get_run(run_id)

    # Comprehensive facts: per-layer KPIs across all layers
    facts = _base_facts(run)
    facts["trust"] = _trust_facts(run)
    facts["metrics"] = _layer_kpis(run.get("layers", {}))

    gen = llm.stream_report(run_id, facts, language)
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/compare/stream")
@limiter.limit(AI_LIMIT)
async def stream_compare(
    request: Request,
    run_id: str = Query(..., description="Run ID to compare strategies"),
    language: Language = Query(default="zh", description="Language: zh or en"),
) -> StreamingResponse:
    """
    Stream multi-strategy comparison analysis.
    """
    run = _get_run(run_id)

    # Strategy COMPARISON uses the strategy definitions/rules (design), not
    # the metric results — that good/bad evaluation belongs to per-layer analysis.
    ids = [run["champion"], run["challenger"]] + ([run["beta"]] if run.get("beta") else [])
    matrices = run.get("layers", {}).get("l4", {}).get("matrices", {})
    facts = {
        "champion": run["champion"],
        "challenger": run["challenger"],
        "beta": run.get("beta"),
        "strategies": {sid: STRATEGIES.get(sid, {}) for sid in ids},
        # Rule differences AND what each difference did to the swap-set, so
        # the comparison explains the result instead of describing two configs.
        "swap_attribution": {
            sid: {
                "rule_diff": m.get("rule_diff", []),
                "swap_in": m.get("swap_in"),
                "swap_out": m.get("swap_out"),
                "swap_in_attribution": m.get("swap_in_attribution", []),
                "swap_out_attribution": m.get("swap_out_attribution", []),
                "swap_in_raroc": m.get("swap_in_raroc"),
            }
            for sid, m in matrices.items()
        },
        "trust": _trust_facts(run),
    }

    gen = llm.stream_compare_strategies(facts, language)
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
