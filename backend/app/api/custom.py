"""Custom strategies / datasets / column-mappings API."""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File, Query

from app.db import repository
from app.db.engine import UPLOADS_DIR
from app.models.schemas import StrategyUpload, ColumnMapping
from app.strategies.sandbox import validate_strategy

router = APIRouter(prefix="/api/custom", tags=["custom"])

_MAX_ROWS = 80000


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #
@router.post("/strategies")
async def create_strategy(body: StrategyUpload) -> dict:
    validation = validate_strategy(body.code)
    if not validation["ok"]:
        raise HTTPException(status_code=400, detail={"error": validation["error"], "validation": validation})

    meta = validation["meta"]
    name = body.name or meta.get("name", "custom")
    sid = repository.create_custom_strategy(
        name=name,
        version=str(meta.get("version", "")),
        role=str(meta.get("role", "challenger")),
        code_text=body.code,
        meta=meta,
    )
    return {"id": sid, "meta": meta, "validation": validation}


@router.get("/strategies")
async def list_strategies() -> dict:
    items = repository.list_custom_strategies()
    return {
        "total": len(items),
        "strategies": [
            {"id": s["id"], "name": s["name"], "version": s["version"],
             "role": s["role"], "meta": s["meta"],
             "required_inputs": s["meta"].get("required_inputs", []) or [],
             "params": s["meta"].get("params", {}) or {},
             "created_at": s["created_at"]}
            for s in items
        ],
    }


@router.get("/strategies/{sid}")
async def get_strategy(sid: str) -> dict:
    s = repository.get_custom_strategy(sid)
    if s is None:
        raise HTTPException(status_code=404, detail=f"strategy not found: {sid}")
    return s


@router.delete("/strategies/{sid}")
async def delete_strategy(sid: str) -> dict:
    ok = repository.delete_custom_strategy(sid)
    if not ok:
        raise HTTPException(status_code=404, detail=f"strategy not found: {sid}")
    return {"deleted": sid}


# --------------------------------------------------------------------------- #
# Datasets
# --------------------------------------------------------------------------- #
@router.post("/datasets")
async def create_dataset(file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    try:
        frame = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not parse CSV: {exc}")

    if len(frame) == 0:
        raise HTTPException(status_code=400, detail="CSV has no rows")

    truncated = len(frame) > _MAX_ROWS
    if truncated:
        frame = frame.iloc[:_MAX_ROWS].copy()

    did = repository._new_id()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = str(UPLOADS_DIR / f"{did}.parquet")
    try:
        frame.to_parquet(file_path, index=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not store dataset: {exc}")

    columns = []
    dtypes = {}
    for col in frame.columns:
        series = frame[col]
        dtypes[col] = str(series.dtype)
        samples = series.dropna().head(3).tolist()
        columns.append({
            "name": col,
            "dtype": str(series.dtype),
            "sample_values": [_jsonable(v) for v in samples],
        })

    name = file.filename or did
    repository.create_custom_dataset(
        name=name, file_path=file_path, n_rows=int(len(frame)),
        columns=columns, dtypes=dtypes, dataset_id=did,
    )
    return {"id": did, "name": name, "columns": columns, "n_rows": int(len(frame)),
            "truncated": truncated}


def _jsonable(v):
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
    except Exception:  # noqa: BLE001
        pass
    return v


@router.get("/datasets")
async def list_datasets() -> dict:
    items = repository.list_custom_datasets()
    return {
        "total": len(items),
        "datasets": [
            {"id": d["id"], "name": d["name"], "n_rows": d["n_rows"],
             "columns": d["columns"], "created_at": d["created_at"]}
            for d in items
        ],
    }


@router.get("/datasets/{did}/columns")
async def dataset_columns(did: str) -> dict:
    d = repository.get_custom_dataset(did)
    if d is None:
        raise HTTPException(status_code=404, detail=f"dataset not found: {did}")
    return {"id": did, "n_rows": d["n_rows"], "columns": d["columns"]}


@router.delete("/datasets/{did}")
async def delete_dataset(did: str) -> dict:
    ok = repository.delete_custom_dataset(did)
    if not ok:
        raise HTTPException(status_code=404, detail=f"dataset not found: {did}")
    return {"deleted": did}


# --------------------------------------------------------------------------- #
# Column mappings
# --------------------------------------------------------------------------- #
@router.post("/mappings")
async def create_mapping(body: ColumnMapping) -> dict:
    dataset = repository.get_custom_dataset(body.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"dataset not found: {body.dataset_id}")
    strategy = repository.get_custom_strategy(body.strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"strategy not found: {body.strategy_id}")

    column_names = {c["name"] for c in dataset["columns"]}
    warnings: list[str] = []

    # required_inputs must all map to existing columns
    required = strategy["meta"].get("required_inputs", []) or []
    for logical in required:
        physical = body.mapping.get(logical)
        if physical is None:
            raise HTTPException(status_code=400,
                                detail=f"required input '{logical}' is not mapped")
        if physical not in column_names:
            raise HTTPException(status_code=400,
                                detail=f"mapped column '{physical}' for '{logical}' not in dataset")

    # role_columns must point at existing columns when supplied
    for role, physical in body.role_columns.items():
        if physical not in column_names:
            raise HTTPException(status_code=400,
                                detail=f"role column '{physical}' for '{role}' not in dataset")

    has_outcome = "outcome" in body.role_columns or "bad" in column_names
    has_score = "score" in body.role_columns or "score" in column_names
    has_protected = any(
        r in body.role_columns or r in column_names
        for r in ("gender", "age_band", "channel")
    )
    if not has_outcome:
        warnings.append("no outcome column mapped: L1/L3/L4 will be skipped")
    if not has_protected:
        warnings.append("no protected attributes mapped: L5 fairness will be skipped")

    mid = repository.create_column_mapping(
        dataset_id=body.dataset_id, strategy_id=body.strategy_id,
        mapping=body.mapping, role_columns=body.role_columns,
    )
    available_layers = {
        "l1": has_outcome,
        "l2": True,
        "l3": has_outcome,
        "l4": has_outcome,
        "l5": has_protected,
    }
    return {"id": mid, "available_layers": available_layers, "warnings": warnings}


@router.get("/mappings")
async def list_mappings(
    dataset_id: str = Query(default=None),
    strategy_id: str = Query(default=None),
) -> dict:
    items = repository.list_column_mappings(dataset_id=dataset_id, strategy_id=strategy_id)
    return {"total": len(items), "mappings": items}
