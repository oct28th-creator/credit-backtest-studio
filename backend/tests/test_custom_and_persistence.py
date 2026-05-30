"""
Tests for the previously-uncovered paths: API-key auth, dataset upload limits,
parquet cleanup on delete, and SQLite run persistence / rehydration.
"""
import importlib
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db import repository
from app.api import experiments

client = TestClient(app)


def _csv_bytes(rows: int = 5) -> bytes:
    lines = ["score,bad,gender"]
    for i in range(rows):
        lines.append(f"{600 + i},{i % 2},{'F' if i % 2 else 'M'}")
    return ("\n".join(lines)).encode()


# ---------------------------------------------------------------------------
# API-key authentication gate
# ---------------------------------------------------------------------------
class TestApiKeyAuth:
    def test_custom_open_when_no_key_configured(self):
        # Default settings have no API key -> auth disabled -> open.
        assert settings.auth_enabled is False
        resp = client.get("/api/custom/datasets")
        assert resp.status_code == 200

    def test_custom_rejected_without_header_when_key_set(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "secret-key")
        resp = client.get("/api/custom/datasets")
        assert resp.status_code == 401

    def test_custom_allowed_with_correct_header(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "secret-key")
        resp = client.get("/api/custom/datasets", headers={"X-API-Key": "secret-key"})
        assert resp.status_code == 200

    def test_custom_rejected_with_wrong_header(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "secret-key")
        resp = client.get("/api/custom/datasets", headers={"X-API-Key": "nope"})
        assert resp.status_code == 401

    def test_ai_status_stays_public_even_with_key(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "secret-key")
        # /status never consumes tokens and must remain reachable for the UI.
        assert client.get("/api/ai/status").status_code == 200

    def test_ai_stream_requires_key(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "secret-key")
        resp = client.post("/api/ai/parse-config/stream", json={"text": "x", "language": "en"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Dataset upload: parsing, row cap, size cap, parquet cleanup on delete
# ---------------------------------------------------------------------------
class TestDatasetUpload:
    def test_upload_and_columns(self):
        resp = client.post(
            "/api/custom/datasets",
            files={"file": ("data.csv", _csv_bytes(8), "text/csv")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_rows"] == 8
        names = {c["name"] for c in body["columns"]}
        assert {"score", "bad", "gender"} <= names

    def test_delete_removes_parquet_file(self, tmp_path):
        resp = client.post(
            "/api/custom/datasets",
            files={"file": ("data.csv", _csv_bytes(4), "text/csv")},
        )
        did = resp.json()["id"]
        stored = repository.get_custom_dataset(did)
        from pathlib import Path
        parquet = Path(stored["file_path"])
        assert parquet.exists()

        del_resp = client.delete(f"/api/custom/datasets/{did}")
        assert del_resp.status_code == 200
        # DB record gone AND file removed (no orphan left on disk).
        assert repository.get_custom_dataset(did) is None
        assert not parquet.exists()

    def test_oversize_upload_rejected(self, monkeypatch):
        from app.api import custom
        # Shrink the cap so we don't have to actually stream 50 MB.
        monkeypatch.setattr(custom, "_MAX_UPLOAD_BYTES", 1024)
        big = b"score,bad\n" + b"600,0\n" * 5000  # well over 1 KB
        resp = client.post(
            "/api/custom/datasets",
            files={"file": ("big.csv", big, "text/csv")},
        )
        assert resp.status_code == 413


# ---------------------------------------------------------------------------
# SQLite run persistence + rehydration (the A3 data-loss fix)
# ---------------------------------------------------------------------------
class TestRunPersistence:
    def test_run_is_persisted_to_sqlite(self):
        payload = {
            "challenger": "v2.3", "champion": "v2.2",
            "sample_id": "consumer_2024q1q2", "language": "en",
        }
        run_id = client.post("/api/experiments/run", json=payload).json()["run_id"]
        stored = repository.get_run(run_id)
        assert stored is not None
        assert stored["result"]["run_id"] == run_id
        assert "layers" in stored["result"]

    def test_rehydrate_restores_runs_into_memory_store(self):
        payload = {
            "challenger": "v2.3", "champion": "v2.2",
            "sample_id": "consumer_2024q1q2", "language": "en",
        }
        run_id = client.post("/api/experiments/run", json=payload).json()["run_id"]

        # Simulate a restart: clear the in-memory store, then rehydrate.
        experiments._RUN_STORE.clear()
        assert run_id not in experiments._RUN_STORE
        loaded = experiments.rehydrate_run_store()
        assert loaded >= 1
        assert run_id in experiments._RUN_STORE
        # And the run is now reachable through the API again.
        assert client.get(f"/api/experiments/{run_id}").status_code == 200

    def test_load_all_runs_skips_bad_json(self):
        # Insert a row with corrupt result JSON directly, then ensure loader
        # skips it rather than crashing.
        conn = repository.get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO runs (run_id, config_json, result_json, snapshot_sha, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                ("bad-json-run", "{}", "{not valid json", "sha", "2020-01-01T00:00:00+00:00"),
            )
            conn.commit()
        finally:
            conn.close()
        runs = repository.load_all_runs()
        assert all(rid != "bad-json-run" for rid, _ in runs)
