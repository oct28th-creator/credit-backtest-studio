"""Shared FastAPI dependencies (authentication, etc.)."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Guard expensive / write endpoints with a static API key.

    Auth is opt-in: when ``settings.api_key`` is empty (the default) this is a
    no-op so local/demo runs and the test-suite keep working. Set the ``API_KEY``
    environment variable to require an ``X-API-Key`` header on protected routers.
    The comparison is constant-time to avoid leaking the key via timing.
    """
    if not settings.auth_enabled:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "API-Key"},
        )
