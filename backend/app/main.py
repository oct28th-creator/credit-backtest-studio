"""
BackTest Studio — FastAPI application entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.security import require_api_token
from app.api import experiments, ai, samples, reports, custom
from app.db.engine import init_db, UPLOADS_DIR
from app.ratelimit import limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("backtest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("BackTest Studio API starting up")
    logger.info("LLM available: %s", settings.llm_available)
    logger.info("CORS origins: %s", settings.cors_list)
    init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    # Rehydrate completed runs from SQLite so they survive a restart.
    loaded = experiments.rehydrate_run_store()
    logger.info("SQLite initialised; uploads dir: %s; runs restored: %d", UPLOADS_DIR, loaded)
    yield
    logger.info("BackTest Studio API shutting down")


app = FastAPI(
    title="BackTest Studio",
    description=(
        "Credit strategy backtesting platform for Black Friday credit limit increases. "
        "Compares Champion, Challenger, and Beta strategies across L1-L5 metric layers."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Per-IP rate limiting (see app/ratelimit.py for budgets)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(experiments.router, dependencies=[Depends(require_api_token)])
app.include_router(ai.router, dependencies=[Depends(require_api_token)])
app.include_router(samples.router, dependencies=[Depends(require_api_token)])
app.include_router(reports.router, dependencies=[Depends(require_api_token)])
app.include_router(custom.router, dependencies=[Depends(require_api_token)])


@app.get("/", tags=["health"])
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "app": "BackTest Studio",
        "version": "1.0.0",
        "llm_available": settings.llm_available,
    }


@app.get("/api/health", tags=["health"])
async def api_health() -> dict:
    """API health check with configuration summary."""
    return {
        "status": "ok",
        "llm_model": settings.deepseek_model if settings.llm_available else None,
        "llm_available": settings.llm_available,
        "cors_origins": settings.cors_list,
    }
