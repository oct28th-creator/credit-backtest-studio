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
def create_run(
    run_id: str,
    config: dict,
    result: dict,
    snapshot_sha: str,
    manifest: Optional[dict] = None,
    parent_run_id: Optional[str] = None,
    root_run_id: Optional[str] = None,
    status: str = "succeeded",
    created_by: str = "user",
    hypothesis: Optional[str] = None,
    tags: Optional[list] = None,
) -> str:
    """Persist a run. Runs are immutable: a variation is a NEW run_id whose
    lineage points at the run it came from, never an overwrite of it."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, config_json, result_json, snapshot_sha,"
            " created_at, manifest_sha, manifest_json, parent_run_id, root_run_id,"
            " status, created_by, hypothesis, tags_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, json.dumps(config), json.dumps(result), snapshot_sha, _now(),
                (manifest or {}).get("manifest_sha"),
                json.dumps(manifest) if manifest else None,
                parent_run_id, root_run_id or run_id, status, created_by,
                hypothesis, json.dumps(tags or []),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def update_run_status(run_id: str, status: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def annotate_run(run_id: str, hypothesis: Optional[str] = None,
                 conclusion: Optional[str] = None,
                 tags: Optional[list] = None) -> bool:
    """Attach the *why* and the *so what* to a run.

    The metrics alone are not reusable knowledge; an agent searching prior work
    needs the question and the finding attached to the numbers."""
    sets, vals = [], []
    if hypothesis is not None:
        sets.append("hypothesis = ?"); vals.append(hypothesis)
    if conclusion is not None:
        sets.append("conclusion = ?"); vals.append(conclusion)
    if tags is not None:
        sets.append("tags_json = ?"); vals.append(json.dumps(tags))
    if not sets:
        return False
    vals.append(run_id)
    conn = get_conn()
    try:
        cur = conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE run_id = ?", vals)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def find_runs_by_manifest(manifest_sha: str, limit: int = 10) -> list[dict]:
    """Prior runs with an identical reproducibility hash — the cache lookup an
    agent should hit before spending compute on a repeat experiment."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT run_id, created_at, created_by, hypothesis, conclusion"
            " FROM runs WHERE manifest_sha = ? ORDER BY created_at DESC LIMIT ?",
            (manifest_sha, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def search_runs(query: Optional[str] = None, tag: Optional[str] = None,
                limit: int = 20) -> list[dict]:
    """Search the experiment registry by recorded question/finding or tag.

    This is the "read before you spend" path: an agent should look for prior
    work here before submitting a new experiment."""
    sql = ("SELECT run_id, created_at, created_by, status, manifest_sha,"
           " hypothesis, conclusion, tags_json FROM runs WHERE 1=1")
    params: list = []
    if query:
        sql += " AND (COALESCE(hypothesis,'') LIKE ? OR COALESCE(conclusion,'') LIKE ?)"
        params += [f"%{query}%", f"%{query}%"]
    if tag:
        sql += " AND COALESCE(tags_json,'') LIKE ?"
        params.append(f'%"{tag}"%')
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    conn = get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.pop("tags_json") or "[]")
        out.append(d)
    return out


def get_lineage(root_run_id: str) -> list[dict]:
    """All runs sharing a root — one experiment thread, in order."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT run_id, parent_run_id, root_run_id, manifest_sha, status,"
            " created_by, created_at, hypothesis, conclusion, tags_json, config_json"
            " FROM runs WHERE root_run_id = ? ORDER BY created_at ASC",
            (root_run_id,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.pop("tags_json") or "[]")
        d["config"] = json.loads(d.pop("config_json") or "{}")
        out.append(d)
    return out


def get_run(run_id: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    keys = row.keys()
    return {
        "run_id": row["run_id"],
        "config": json.loads(row["config_json"]) if row["config_json"] else {},
        "result": json.loads(row["result_json"]) if row["result_json"] else {},
        "snapshot_sha": row["snapshot_sha"],
        "created_at": row["created_at"],
        "manifest_sha": row["manifest_sha"] if "manifest_sha" in keys else None,
        "manifest": (json.loads(row["manifest_json"])
                     if "manifest_json" in keys and row["manifest_json"] else None),
        "parent_run_id": row["parent_run_id"] if "parent_run_id" in keys else None,
        "root_run_id": row["root_run_id"] if "root_run_id" in keys else row["run_id"],
        "status": row["status"] if "status" in keys else "succeeded",
        "created_by": row["created_by"] if "created_by" in keys else "user",
        "hypothesis": row["hypothesis"] if "hypothesis" in keys else None,
        "conclusion": row["conclusion"] if "conclusion" in keys else None,
        "tags": json.loads(row["tags_json"]) if "tags_json" in keys and row["tags_json"] else [],
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


def load_all_runs() -> "list[tuple[str, dict]]":
    """Return every persisted run's frontend-shaped result, oldest first.

    Used to rehydrate the in-memory run store on startup so completed runs
    survive a service restart. Rows whose result JSON is unreadable are skipped,
    and so are runs that never produced one — a queued/running/failed job has a
    row (that is how its status is observable) but no metrics to serve.
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT run_id, result_json, status FROM runs ORDER BY created_at ASC"
        ).fetchall()
    finally:
        conn.close()
    out: list[tuple[str, dict]] = []
    for row in rows:
        if (row["status"] or "succeeded") != "succeeded":
            continue
        try:
            result = json.loads(row["result_json"]) if row["result_json"] else None
        except (ValueError, TypeError):
            continue
        if isinstance(result, dict) and result.get("layers"):
            out.append((row["run_id"], result))
    return out
