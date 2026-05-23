"""
BackTest Studio — FastAPI application entry point.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import experiments, ai, samples, reports


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print("  BackTest Studio API starting up")
    print(f"  LLM available: {settings.llm_available}")
    print(f"  CORS origins: {settings.cors_list}")
    print("=" * 60)
    yield
    print("BackTest Studio API shutting down")


app = FastAPI(
    title="BackTest Studio",
    description=(
        "Credit strategy backtesting platform for Black Friday credit limit increases. "
        "Compares Champion, Challenger, and Beta strategies across L1-L5 metric layers."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(experiments.router)
app.include_router(ai.router)
app.include_router(samples.router)
app.include_router(reports.router)


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
