"""Session budgets.

An agent that can call ``submit_experiment`` in a loop can spend unbounded
compute. Every agent-initiated action is charged against a session budget, and
the budget is enforced in the tool layer — not in the prompt, which an LLM can
talk itself out of.
"""
from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from typing import Optional

_MAX_SESSIONS = 200


class BudgetExceeded(Exception):
    """Raised when an action would exceed the session's remaining budget."""


@dataclass
class Budget:
    max_experiments: int = 12
    max_llm_calls: int = 12
    max_wall_seconds: int = 900

    def clamp(self) -> "Budget":
        """Keep a caller-supplied budget inside platform limits."""
        return Budget(
            max_experiments=max(1, min(self.max_experiments, 40)),
            max_llm_calls=max(1, min(self.max_llm_calls, 40)),
            max_wall_seconds=max(30, min(self.max_wall_seconds, 3600)),
        )


@dataclass
class Session:
    session_id: str
    goal: str = ""
    budget: Budget = field(default_factory=Budget)
    created_at: float = field(default_factory=time.time)
    experiments_spent: int = 0
    llm_calls_spent: int = 0
    run_ids: list[str] = field(default_factory=list)
    cached_run_ids: list[str] = field(default_factory=list)
    status: str = "active"

    # ------------------------------------------------------------------ #
    def elapsed(self) -> float:
        return time.time() - self.created_at

    def remaining_experiments(self) -> int:
        return max(self.budget.max_experiments - self.experiments_spent, 0)

    def check_wall_clock(self) -> None:
        if self.elapsed() > self.budget.max_wall_seconds:
            self.status = "budget_exhausted"
            raise BudgetExceeded(
                f"session wall-clock budget exhausted "
                f"({self.budget.max_wall_seconds}s)"
            )

    def spend_experiment(self, n: int = 1) -> None:
        self.check_wall_clock()
        if self.experiments_spent + n > self.budget.max_experiments:
            self.status = "budget_exhausted"
            raise BudgetExceeded(
                f"experiment budget exhausted "
                f"({self.experiments_spent}/{self.budget.max_experiments} used, "
                f"{n} more requested)"
            )
        self.experiments_spent += n

    def spend_llm_call(self, n: int = 1) -> None:
        self.check_wall_clock()
        if self.llm_calls_spent + n > self.budget.max_llm_calls:
            self.status = "budget_exhausted"
            raise BudgetExceeded(
                f"LLM call budget exhausted "
                f"({self.llm_calls_spent}/{self.budget.max_llm_calls} used)"
            )
        self.llm_calls_spent += n

    def record_run(self, run_id: str, cached: bool = False) -> None:
        (self.cached_run_ids if cached else self.run_ids).append(run_id)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["elapsed_s"] = round(self.elapsed(), 1)
        d["remaining_experiments"] = self.remaining_experiments()
        return d


_SESSIONS: "OrderedDict[str, Session]" = OrderedDict()


def create(goal: str = "", budget: Optional[Budget] = None) -> Session:
    session = Session(
        session_id=uuid.uuid4().hex[:12],
        goal=goal,
        budget=(budget or Budget()).clamp(),
    )
    _SESSIONS[session.session_id] = session
    while len(_SESSIONS) > _MAX_SESSIONS:
        _SESSIONS.popitem(last=False)
    return session


def get(session_id: str) -> Optional[Session]:
    return _SESSIONS.get(session_id)


def list_sessions(limit: int = 50) -> list[dict]:
    return [s.to_dict() for s in list(reversed(_SESSIONS.values()))[:limit]]


def reset() -> None:
    """Test hook."""
    _SESSIONS.clear()
