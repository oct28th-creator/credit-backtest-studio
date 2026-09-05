"""Simulation environments.

A backtest is only as trustworthy as the world it assumes. Three levels:

  L0a replay            history replayed; every applicant's outcome is known
  L0b reject inference  outcomes hidden for the population the champion
                        rejected, then estimated — the real-world condition
  L0c behavioural       acceptance, utilisation and migration respond to the
                        policy (not built yet)

Every environment declares a ``confidence`` band, and that band travels with
the run. A conclusion is only as strong as the environment that produced it,
and this package is where that gets made explicit instead of assumed.
"""
from app.envs.base import (  # noqa: F401
    ENVIRONMENTS, Environment, get_environment, list_environments,
)
