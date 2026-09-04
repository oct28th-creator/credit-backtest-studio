"""Optional shared-secret auth.

The platform is single-tenant by design, but the API may be exposed on a
public IP. When ``APP_API_TOKEN`` is unset, auth is disabled and behaviour is
unchanged (backward compatible). When set, every /api route requires the
``X-API-Token`` header to match.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from app.config import settings


def require_api_token(request: Request) -> None:
    if not settings.auth_enabled:
        return
    token = request.headers.get("x-api-token", "")
    if token != settings.app_api_token:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")
