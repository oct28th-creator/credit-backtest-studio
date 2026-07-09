"""End-to-end tests for the custom strategy/dataset pipeline via the API.

Covers: CSV dataset upload -> strategy upload -> column mapping (including its
validation branches) -> POST /api/run with custom refs -> layer assertions,
plus the error paths (unknown refs, builtin-on-custom-dataset, bad mappings).
"""
import io

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

N_ROWS = 1500


def _csv_bytes(n=N_ROWS, seed=11) -> bytes:
    rng = np.random.default_rng(seed)
    score = rng.uniform(560.0, 820.0, n)
    bad_prob = np.clip(1.3 - score / 650.0, 0.02, 0.85)
    frame = pd.DataFrame({
        "credit_score": np.round(score, 1),
        "debt_ratio": np.round(rng.uniform(0.05, 0.9, n), 3),
        "is_bad": (rng.uniform(0, 1, n) < bad_prob).astype(int),
        "sex": rng.integers(0, 2, n),
    })
    buf = io.BytesIO()
    frame.to_csv(buf, index=False)
    return buf.getvalue()


def _strategy_code(name: str, cutoff: float, role: str) -> str:
    return f'''
STRATEGY_META = {{
    "name": "{name}",
    "version": "1.0",
    "role": "{role}",
    "required_inputs": ["score"],
    "params": {{"cutoff": {{"type": "float", "default": {cutoff}}}}},
}}

def score(features, params):
    s = features["score"]
    return (850.0 - s) / 350.0

def approve(features, pd_hat, params):
    return pd_hat < params.get("cutoff", {cutoff})
'''


@pytest.fixture(scope="module")
def dataset_id():
    resp = client.post(
        "/api/custom/datasets",
        files={"file": ("book.csv", _csv_bytes(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    yield body["id"]
    client.delete(f"/api/custom/datasets/{body['id']}")


@pytest.fixture(scope="module")
def champion_id():
    resp = client.post("/api/custom/strategies",
                       json={"code": _strategy_code("e2e-champ", 0.50, "champion")})
    assert resp.status_code == 200, resp.text
    sid = resp.json()["id"]
    yield sid
    client.delete(f"/api/custom/strategies/{sid}")


@pytest.fixture(scope="module")
def challenger_id():
    resp = client.post("/api/custom/strategies",
                       json={"code": _strategy_code("e2e-chall", 0.60, "challenger")})
    assert resp.status_code == 200, resp.text
    sid = resp.json()["id"]
    yield sid
    client.delete(f"/api/custom/strategies/{sid}")


@pytest.fixture(scope="module")
def mapping_id(dataset_id, champion_id):
    resp = client.post("/api/custom/mappings", json={
        "dataset_id": dataset_id,
        "strategy_id": champion_id,
        "mapping": {"score": "credit_score"},
        "role_columns": {"outcome": "is_bad", "score": "credit_score", "gender": "sex"},
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

class TestDatasetUpload:
    def test_upload_reports_columns_and_rows(self, dataset_id):
        resp = client.get(f"/api/custom/datasets/{dataset_id}/columns")
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_rows"] == N_ROWS
        names = {c["name"] for c in body["columns"]}
        assert names == {"credit_score", "debt_ratio", "is_bad", "sex"}
        for col in body["columns"]:
            assert len(col["sample_values"]) > 0

    def test_unparseable_csv_rejected(self):
        resp = client.post(
            "/api/custom/datasets",
            files={"file": ("bad.csv", b'a,b\n1,"unclosed\n2', "text/csv")},
        )
        assert resp.status_code == 400
        assert "could not parse CSV" in resp.json()["detail"]

    def test_empty_csv_rejected(self):
        resp = client.post(
            "/api/custom/datasets",
            files={"file": ("empty.csv", b"a,b,c\n", "text/csv")},
        )
        assert resp.status_code == 400
        assert "no rows" in resp.json()["detail"]


class TestStrategyUpload:
    def test_invalid_code_rejected_with_validation_detail(self):
        resp = client.post("/api/custom/strategies", json={"code": "def broken(:\n"})
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "syntax error" in detail["error"]

    def test_get_unknown_strategy_404(self):
        assert client.get("/api/custom/strategies/nope").status_code == 404

    def test_delete_unknown_strategy_404(self):
        assert client.delete("/api/custom/strategies/nope").status_code == 404

    def test_listed_after_upload(self, champion_id):
        body = client.get("/api/custom/strategies").json()
        ids = {s["id"] for s in body["strategies"]}
        assert champion_id in ids


# ---------------------------------------------------------------------------
# Column mappings
# ---------------------------------------------------------------------------

class TestMappingValidation:
    def test_full_mapping_enables_all_layers(self, dataset_id, champion_id):
        resp = client.post("/api/custom/mappings", json={
            "dataset_id": dataset_id,
            "strategy_id": champion_id,
            "mapping": {"score": "credit_score"},
            "role_columns": {"outcome": "is_bad", "gender": "sex"},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["available_layers"] == {
            "l1": True, "l2": True, "l3": True, "l4": True, "l5": True}
        assert body["warnings"] == []

    def test_mapping_without_outcome_warns_and_disables_layers(self, dataset_id, champion_id):
        resp = client.post("/api/custom/mappings", json={
            "dataset_id": dataset_id,
            "strategy_id": champion_id,
            "mapping": {"score": "credit_score"},
            "role_columns": {},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["available_layers"]["l1"] is False
        assert body["available_layers"]["l2"] is True
        assert any("no outcome" in w for w in body["warnings"])
        assert any("no protected" in w for w in body["warnings"])

    def test_unknown_dataset_404(self, champion_id):
        resp = client.post("/api/custom/mappings", json={
            "dataset_id": "nope", "strategy_id": champion_id,
            "mapping": {"score": "credit_score"}, "role_columns": {},
        })
        assert resp.status_code == 404
        assert "dataset not found" in resp.json()["detail"]

    def test_unknown_strategy_404(self, dataset_id):
        resp = client.post("/api/custom/mappings", json={
            "dataset_id": dataset_id, "strategy_id": "nope",
            "mapping": {"score": "credit_score"}, "role_columns": {},
        })
        assert resp.status_code == 404
        assert "strategy not found" in resp.json()["detail"]

    def test_unmapped_required_input_400(self, dataset_id, champion_id):
        resp = client.post("/api/custom/mappings", json={
            "dataset_id": dataset_id, "strategy_id": champion_id,
            "mapping": {}, "role_columns": {},
        })
        assert resp.status_code == 400
        assert "'score' is not mapped" in resp.json()["detail"]

    def test_mapping_to_nonexistent_column_400(self, dataset_id, champion_id):
        resp = client.post("/api/custom/mappings", json={
            "dataset_id": dataset_id, "strategy_id": champion_id,
            "mapping": {"score": "no_such_col"}, "role_columns": {},
        })
        assert resp.status_code == 400
        assert "no_such_col" in resp.json()["detail"]

    def test_role_column_to_nonexistent_column_400(self, dataset_id, champion_id):
        resp = client.post("/api/custom/mappings", json={
            "dataset_id": dataset_id, "strategy_id": champion_id,
            "mapping": {"score": "credit_score"},
            "role_columns": {"outcome": "no_such_col"},
        })
        assert resp.status_code == 400
        assert "no_such_col" in resp.json()["detail"]

    def test_list_mappings_filters_by_dataset(self, dataset_id, mapping_id):
        body = client.get(f"/api/custom/mappings?dataset_id={dataset_id}").json()
        assert body["total"] >= 1
        assert all(m["dataset_id"] == dataset_id for m in body["mappings"])


# ---------------------------------------------------------------------------
# Custom run end-to-end
# ---------------------------------------------------------------------------

class TestCustomRun:
    @pytest.fixture(scope="class")
    def run(self, dataset_id, champion_id, challenger_id, mapping_id):
        resp = client.post("/api/experiments/run", json={
            "champion_ref": f"custom:{champion_id}",
            "challenger_ref": f"custom:{challenger_id}",
            "dataset_ref": f"custom:{dataset_id}",
            "mapping_id": mapping_id,
        })
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_run_reports_dataset_size(self, run):
        assert run["sample_size"] == N_ROWS

    def test_layers_l1_to_l5_present(self, run):
        for layer in ("l1", "l2", "l3", "l4", "l5"):
            assert layer in run["layers"], layer

    def test_l1_kpis_computed_for_both_strategies(self, run, champion_id, challenger_id):
        kpis = {k["version"]: k for k in run["layers"]["l1"]["kpis"]}
        assert set(kpis) == {f"custom:{champion_id}", f"custom:{challenger_id}"}
        for k in kpis.values():
            assert 0.5 < k["auc"] <= 1.0

    def test_l2_challenger_approves_more_than_champion(self, run, champion_id, challenger_id):
        kpis = {k["version"]: k for k in run["layers"]["l2"]["kpis"]}
        champ = kpis[f"custom:{champion_id}"]["approval_rate"]
        chall = kpis[f"custom:{challenger_id}"]["approval_rate"]
        assert chall > champ  # looser cutoff

    def test_l4_swap_matrix_keyed_by_challenger(self, run, challenger_id):
        matrices = run["layers"]["l4"]["matrices"]
        assert f"custom:{challenger_id}" in matrices
        m = matrices[f"custom:{challenger_id}"]
        quadrant_total = (m["double_approve"]["count"] + m["swap_in"]["count"]
                          + m["swap_out"]["count"] + m["double_reject"]["count"])
        assert quadrant_total == N_ROWS

    def test_run_is_retrievable_afterwards(self, run):
        resp = client.get(f"/api/experiments/{run['run_id']}")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run["run_id"]

    def test_custom_strategy_on_builtin_dataset(self, champion_id, challenger_id):
        resp = client.post("/api/experiments/run", json={
            "champion_ref": "builtin:v2.2",
            "challenger_ref": f"custom:{challenger_id}",
            "dataset_ref": "builtin:bf2024",
        })
        assert resp.status_code == 200, resp.text
        kpis = {k["version"] for k in resp.json()["layers"]["l2"]["kpis"]}
        # the config's default beta (v2.4-Beta) also joins builtin-dataset runs
        assert {"builtin:v2.2", f"custom:{challenger_id}"} <= kpis


class TestCustomRunErrors:
    def test_builtin_strategy_on_custom_dataset_400(self, dataset_id, challenger_id, mapping_id):
        resp = client.post("/api/experiments/run", json={
            "champion_ref": "builtin:v2.2",
            "challenger_ref": f"custom:{challenger_id}",
            "dataset_ref": f"custom:{dataset_id}",
            "mapping_id": mapping_id,
        })
        assert resp.status_code == 400
        assert "cannot run on a custom dataset" in resp.json()["detail"]

    def test_unknown_custom_strategy_400(self, dataset_id, challenger_id):
        resp = client.post("/api/experiments/run", json={
            "champion_ref": "custom:doesnotexist",
            "challenger_ref": f"custom:{challenger_id}",
            "dataset_ref": f"custom:{dataset_id}",
        })
        assert resp.status_code == 400
        assert "Unknown custom champion" in resp.json()["detail"]

    def test_invalid_ref_format_400(self, dataset_id, challenger_id):
        resp = client.post("/api/experiments/run", json={
            "champion_ref": "bogus:v2.2",
            "challenger_ref": f"custom:{challenger_id}",
            "dataset_ref": f"custom:{dataset_id}",
        })
        assert resp.status_code == 400
        assert "Invalid champion ref" in resp.json()["detail"]

    def test_unknown_custom_dataset_400(self, champion_id, challenger_id):
        resp = client.post("/api/experiments/run", json={
            "champion_ref": f"custom:{champion_id}",
            "challenger_ref": f"custom:{challenger_id}",
            "dataset_ref": "custom:doesnotexist",
        })
        assert resp.status_code == 400
        assert "Unknown custom dataset" in resp.json()["detail"]

    def test_crashing_strategy_maps_to_400(self, dataset_id, mapping_id, champion_id):
        code = '''
STRATEGY_META = {
    "name": "crasher", "version": "1.0", "role": "challenger",
    "required_inputs": ["score"],
    "params": {"explode": {"type": "bool", "default": False}},
}

def score(features, params):
    if params.get("explode"):
        raise RuntimeError("boom at runtime")
    return features["score"] * 0.0

def approve(features, pd_hat, params):
    if len(features["score"]) > 200:
        raise RuntimeError("boom on real data")
    return pd_hat >= 0.0
'''
        up = client.post("/api/custom/strategies", json={"code": code})
        assert up.status_code == 200, up.text  # passes 100-row trial validation
        sid = up.json()["id"]
        try:
            resp = client.post("/api/experiments/run", json={
                "champion_ref": f"custom:{champion_id}",
                "challenger_ref": f"custom:{sid}",
                "dataset_ref": f"custom:{dataset_id}",
                "mapping_id": mapping_id,
            })
            assert resp.status_code == 400
            assert "boom on real data" in resp.json()["detail"]
        finally:
            client.delete(f"/api/custom/strategies/{sid}")
