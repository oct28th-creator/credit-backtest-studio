"""
Samples router: list available samples and strategy definitions.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.data.fixtures import SAMPLES, STRATEGIES

router = APIRouter(prefix="/api/samples", tags=["samples"])


@router.get("")
async def list_samples() -> dict:
    """List all available sample configurations."""
    return {
        "samples": SAMPLES,
        "total": len(SAMPLES),
    }


@router.get("/strategies")
async def list_strategies() -> dict:
    """
    List all available strategy definitions with their defaults.
    Returns metadata including role, parameters, and rule details.
    """
    strategies_list = []
    for sid, s in STRATEGIES.items():
        strategies_list.append({
            "id": s["id"],
            "name": s["name"],
            "nickname": s["nickname"],
            "role": s["role"],
            "desc_zh": s["desc_zh"],
            "desc_en": s["desc_en"],
            "score_cutoff": s["score_cutoff"],
            "dti_limit": s["dti_limit"],
            "mob_months": s["mob_months"],
            "mob_dpd_max": s["mob_dpd_max"],
            "limit_increase_min": s["limit_increase_min"],
            "limit_increase_max": s["limit_increase_max"],
            "anti_fraud": s["anti_fraud"],
            "online_since": s.get("online_since"),
            "rules": s["rules"],
        })

    # Defaults for UI initialization
    defaults = {
        "challenger": "v2.3",
        "champion": "v2.2",
        "beta_options": ["v2.4-Beta", "v2.5-RC"],
        "default_beta": "v2.4-Beta",
        "default_sample": "consumer_2024q1q2",
    }

    return {
        "strategies": strategies_list,
        "total": len(strategies_list),
        "defaults": defaults,
    }
