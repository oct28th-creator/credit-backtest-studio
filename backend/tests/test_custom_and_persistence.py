"""
Tests for the previously-uncovered paths: dataset upload limits, parquet
cleanup on delete, and SQLite run persistence / rehydration.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.db import repository
from app.api import experiments

client = TestClient(app)


def _csv_bytes(rows: int = 5) -> bytes:
    lines = ["score,bad,gender"]
    for i in range(rows):
        lines.append(f"{600 + i},{i % 2},{'F' if i % 2 else 'M'}")
    return ("\n".join(lines)).encode()


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


# ---------------------------------------------------------------------------
# Repository CRUD not reachable through the API tests above
# ---------------------------------------------------------------------------
class TestRepositoryCrud:
    def test_dataset_roundtrip_and_listing(self, tmp_path):
        did = repository.create_custom_dataset(
            name="repo-ds", file_path=str(tmp_path / "x.parquet"), n_rows=5,
            columns=[{"name": "a", "dtype": "int64", "sample_values": [1]}],
            dtypes={"a": "int64"},
        )
        try:
            assert any(d["id"] == did for d in repository.list_custom_datasets())
            got = repository.get_custom_dataset(did)
            assert got["name"] == "repo-ds"
            assert got["columns"][0]["name"] == "a"
        finally:
            assert repository.delete_custom_dataset(did) is True
        assert repository.get_custom_dataset(did) is None
        assert repository.delete_custom_dataset(did) is False

    def test_mapping_roundtrip_filters_and_delete(self):
        sid = repository.create_custom_strategy(
            name="repo-strat", version="1", role="challenger",
            code_text="# code", meta={"required_inputs": []},
        )
        did = repository.create_custom_dataset(
            name="repo-ds2", file_path="/tmp/none.parquet", n_rows=1,
            columns=[], dtypes={},
        )
        mid = repository.create_column_mapping(
            dataset_id=did, strategy_id=sid,
            mapping={"score": "a"}, role_columns={"outcome": "b"},
        )
        try:
            got = repository.get_column_mapping(mid)
            assert got["mapping"] == {"score": "a"}
            assert got["role_columns"] == {"outcome": "b"}

            by_ds = repository.list_column_mappings(dataset_id=did)
            assert [m["id"] for m in by_ds] == [mid]
            by_strat = repository.list_column_mappings(strategy_id=sid)
            assert [m["id"] for m in by_strat] == [mid]
            assert repository.list_column_mappings(dataset_id="nope") == []
        finally:
            assert repository.delete_column_mapping(mid) is True
            repository.delete_custom_dataset(did)
            repository.delete_custom_strategy(sid)
        assert repository.get_column_mapping(mid) is None
        assert repository.delete_column_mapping(mid) is False

    def test_list_runs_metadata_shape_and_limit(self):
        from app.db.engine import get_conn

        repository.create_run("run-list-a", {"c": 1}, {"r": 1}, "sha-a")
        repository.create_run("run-list-b", {"c": 2}, {"r": 2}, "sha-b")
        try:
            runs = repository.list_runs(limit=200)
            ids = [r["run_id"] for r in runs]
            assert "run-list-a" in ids and "run-list-b" in ids
            for r in runs:
                assert set(r.keys()) == {"run_id", "snapshot_sha", "created_at"}
            assert len(repository.list_runs(limit=1)) == 1
        finally:
            # There is no repository.delete_run; remove the synthetic rows via
            # SQL so a later lifespan rehydration doesn't load these minimal
            # payloads (the /history endpoint 500s on runs without full shape).
            conn = get_conn()
            try:
                conn.execute("DELETE FROM runs WHERE run_id LIKE 'run-list-%'")
                conn.commit()
            finally:
                conn.close()
