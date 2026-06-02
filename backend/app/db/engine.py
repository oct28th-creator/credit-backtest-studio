"""SQLite engine setup and schema bootstrap."""
from __future__ import annotations

import sqlite3
from pathlib import Path

# backend/data/backtest_studio.db  (engine.py -> db -> app -> backend)
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = _BACKEND_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "backtest_studio.db"


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL lets readers (API) and writers (run persistence) coexist instead of
    # hitting "database is locked"; busy_timeout makes the rare writer
    # contention block briefly rather than failing immediately.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_strategies (
    id          TEXT PRIMARY KEY,
    name        TEXT,
    version     TEXT,
    role        TEXT,
    code_text   TEXT NOT NULL,
    meta_json   TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS custom_datasets (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    file_path    TEXT NOT NULL,
    n_rows       INTEGER,
    columns_json TEXT,
    dtypes_json  TEXT,
    created_at   TEXT
);

CREATE TABLE IF NOT EXISTS column_mappings (
    id                TEXT PRIMARY KEY,
    dataset_id        TEXT,
    strategy_id       TEXT,
    mapping_json      TEXT,
    role_columns_json TEXT,
    created_at        TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    config_json  TEXT,
    result_json  TEXT,
    snapshot_sha TEXT,
    created_at   TEXT
);
"""


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
