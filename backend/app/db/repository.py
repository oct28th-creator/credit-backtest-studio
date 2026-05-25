"""Thin CRUD layer over the SQLite tables (standard-library sqlite3)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.db.engine import get_conn


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# custom_strategies
# --------------------------------------------------------------------------- #
def create_custom_strategy(name: str, version: str, role: str, code_text: str, meta: dict) -> str:
    sid = _new_id()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO custom_strategies (id, name, version, role, code_text, meta_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, name, version, role, code_text, json.dumps(meta), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return sid


def _row_to_strategy(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "version": row["version"],
        "role": row["role"],
        "code_text": row["code_text"],
        "meta": json.loads(row["meta_json"]) if row["meta_json"] else {},
        "created_at": row["created_at"],
    }


def get_custom_strategy(sid: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM custom_strategies WHERE id = ?", (sid,)).fetchone()
    finally:
        conn.close()
    return _row_to_strategy(row) if row else None


def list_custom_strategies() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM custom_strategies ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    return [_row_to_strategy(r) for r in rows]


def delete_custom_strategy(sid: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM custom_strategies WHERE id = ?", (sid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# custom_datasets
# --------------------------------------------------------------------------- #
def create_custom_dataset(name: str, file_path: str, n_rows: int, columns: list, dtypes: dict,
                          dataset_id: Optional[str] = None) -> str:
    did = dataset_id or _new_id()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO custom_datasets (id, name, file_path, n_rows, columns_json, dtypes_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (did, name, file_path, n_rows, json.dumps(columns), json.dumps(dtypes), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return did


def _row_to_dataset(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "file_path": row["file_path"],
        "n_rows": row["n_rows"],
        "columns": json.loads(row["columns_json"]) if row["columns_json"] else [],
        "dtypes": json.loads(row["dtypes_json"]) if row["dtypes_json"] else {},
        "created_at": row["created_at"],
    }


def get_custom_dataset(did: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM custom_datasets WHERE id = ?", (did,)).fetchone()
    finally:
        conn.close()
    return _row_to_dataset(row) if row else None


def list_custom_datasets() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM custom_datasets ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    return [_row_to_dataset(r) for r in rows]


def delete_custom_dataset(did: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM custom_datasets WHERE id = ?", (did,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# column_mappings
# --------------------------------------------------------------------------- #
def create_column_mapping(dataset_id: str, strategy_id: str, mapping: dict, role_columns: dict) -> str:
    mid = _new_id()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO column_mappings (id, dataset_id, strategy_id, mapping_json, role_columns_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (mid, dataset_id, strategy_id, json.dumps(mapping), json.dumps(role_columns), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return mid


def _row_to_mapping(row) -> dict:
    return {
        "id": row["id"],
        "dataset_id": row["dataset_id"],
        "strategy_id": row["strategy_id"],
        "mapping": json.loads(row["mapping_json"]) if row["mapping_json"] else {},
        "role_columns": json.loads(row["role_columns_json"]) if row["role_columns_json"] else {},
        "created_at": row["created_at"],
    }


def get_column_mapping(mid: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM column_mappings WHERE id = ?", (mid,)).fetchone()
    finally:
        conn.close()
    return _row_to_mapping(row) if row else None


def list_column_mappings(dataset_id: Optional[str] = None, strategy_id: Optional[str] = None) -> list[dict]:
    clauses, args = [], []
    if dataset_id:
        clauses.append("dataset_id = ?")
        args.append(dataset_id)
    if strategy_id:
        clauses.append("strategy_id = ?")
        args.append(strategy_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM column_mappings{where} ORDER BY created_at DESC", args
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_mapping(r) for r in rows]


def delete_column_mapping(mid: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM column_mappings WHERE id = ?", (mid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# runs
# --------------------------------------------------------------------------- #
def create_run(run_id: str, config: dict, result: dict, snapshot_sha: str) -> str:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, config_json, result_json, snapshot_sha, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (run_id, json.dumps(config), json.dumps(result), snapshot_sha, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def get_run(run_id: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "config": json.loads(row["config_json"]) if row["config_json"] else {},
        "result": json.loads(row["result_json"]) if row["result_json"] else {},
        "snapshot_sha": row["snapshot_sha"],
        "created_at": row["created_at"],
    }


def list_runs(limit: int = 50) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT run_id, snapshot_sha, created_at FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
