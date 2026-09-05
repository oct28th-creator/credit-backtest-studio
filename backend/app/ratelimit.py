"""Per-client rate limiting for compute-heavy and LLM-backed endpoints.

Limits are keyed by client IP. Set RATE_LIMIT_ENABLED=0 to disable (used by
the test suite, which exercises endpoints far faster than a real client).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address, enabled=settings.rate_limit_enabled)

# One place to tune the budgets:
RUN_LIMIT = "10/minute"      # full backtest: CPU-heavy L1-L5 computation
RESLICE_LIMIT = "90/minute"  # interactive slicing: a user clicking through
                             # dimensions hit the old 30/min ceiling
AI_LIMIT = "20/minute"       # DeepSeek-backed streams: provider quota + cost
AGENT_LIMIT = "5/minute"     # agent loop: many backtests + several LLM calls each
