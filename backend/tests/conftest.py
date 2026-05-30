"""Shared pytest fixtures / test bootstrap.

The app initialises the SQLite schema in its lifespan handler, but a
module-level ``TestClient(app)`` does not run the lifespan, so the tables would
not exist during tests. Initialise the schema once per session here so the
persistence paths (runs, custom datasets) are exercised for real.
"""
import pytest

from app.db.engine import init_db


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db():
    init_db()
    yield
