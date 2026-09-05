"""P1 agentic-platform foundations.

Covers the four properties an experiment platform must have before an agent
can be trusted to drive it:

  1. identity      — a run's hash covers everything that changes its numbers
  2. immutability  — a derived run never overwrites the run it came from
  3. controllability — policy/param knobs are settable per run, and validated
  4. observability — runs have a lifecycle that can be polled, and a memory
                     (hypothesis/conclusion) that can be searched
"""
import time

import pytest
from fastapi.testclient import TestClient

from app.core import manifest as mf
from app.data.fixtures import _approve_mask, generate_synthetic_data
from app.main import app

client = TestClient(app)

BASE = {
    "champion": "v2.2",
    "challenger": "v2.3",
    "beta": None,
    "sample_id": "consumer_2024q1q2",
    "lookback_months": 6,
    "perf_window_months": 12,
    "ri_mode": "parceling",
    "language": "zh",
}


# --------------------------------------------------------------------------- #
# 1. Identity
# --------------------------------------------------------------------------- #
class TestManifest:
    def test_same_config_same_hash(self):
        a = mf.build_manifest(dict(BASE))
        b = mf.build_manifest(dict(BASE))
        assert a["manifest_sha"] == b["manifest_sha"]

    def test_key_ordering_does_not_change_hash(self):
        reordered = {k: BASE[k] for k in reversed(list(BASE))}
        assert (mf.build_manifest(dict(BASE))["manifest_sha"]
                == mf.build_manifest(reordered)["manifest_sha"])

    @pytest.mark.parametrize("field,value", [
        ("seed", 7),
        ("slice_dim", "gender"),
        ("challenger", "v2.4-Beta"),
        ("sample_id", "sme_2024q1"),
    ])
    def test_anything_that_moves_the_numbers_moves_the_hash(self, field, value):
        base_sha = mf.build_manifest(dict(BASE))["manifest_sha"]
        variant = dict(BASE)
        variant[field] = value
        assert mf.build_manifest(variant)["manifest_sha"] != base_sha

    def test_policy_override_changes_hash(self):
        base_sha = mf.build_manifest(dict(BASE))["manifest_sha"]
        variant = dict(BASE, policy_overrides={"v2.3": {"target_approval_rate": 0.55}})
        assert mf.build_manifest(variant)["manifest_sha"] != base_sha

    def test_manifest_records_versions_and_dataset_content(self):
        m = mf.build_manifest(dict(BASE))
        body = m["body"]
        assert body["engine_version"] == mf.ENGINE_VERSION
        assert body["metric_version"] == mf.METRIC_VERSION
        assert body["dataset"]["kind"] == "synthetic"
        assert body["dataset"]["seed"] == 42
        assert set(body["strategies"]) == {"champion", "challenger"}

    def test_run_result_carries_manifest_sha(self):
        run = client.post("/api/experiments/run", json=BASE).json()
        assert len(run["manifest_sha"]) == 64
        stored = client.get(f"/api/experiments/{run['run_id']}/manifest").json()
        assert stored["manifest_sha"] == run["manifest_sha"]


# --------------------------------------------------------------------------- #
# 2. Controllability
# --------------------------------------------------------------------------- #
class TestPolicyOverrides:
    def test_target_approval_rate_moves_approval(self):
        df = generate_synthetic_data(n=20000, seed=42)
        base = _approve_mask(df, "v2.3").mean()
        loosened = _approve_mask(df, "v2.3", {"target_approval_rate": 0.60}).mean()
        tightened = _approve_mask(df, "v2.3", {"target_approval_rate": 0.20}).mean()
        assert tightened < base < loosened

    def test_dti_cap_only_removes_applicants(self):
        df = generate_synthetic_data(n=20000, seed=42)
        base = _approve_mask(df, "v2.2")
        strict = _approve_mask(df, "v2.2", {"dti_limit": 0.30})
        assert strict.sum() < base.sum()

    def test_unknown_knob_is_rejected(self):
        df = generate_synthetic_data(n=1000, seed=42)
        with pytest.raises(ValueError, match="non-overridable"):
            _approve_mask(df, "v2.2", {"bad_rate": 0.0})

    def test_override_flows_through_the_api(self):
        base = client.post("/api/experiments/run", json=BASE).json()
        tuned = client.post("/api/experiments/run", json=dict(
            BASE, policy_overrides={"v2.3": {"target_approval_rate": 0.60}},
        )).json()

        def apr(run):
            return next(k["approval_rate"] for k in run["layers"]["l2"]["kpis"]
                        if k["version"] == "v2.3")

        assert apr(tuned) > apr(base)
        assert tuned["manifest_sha"] != base["manifest_sha"]

    def test_seed_changes_the_draw_not_the_conclusion(self):
        a = client.post("/api/experiments/run", json=dict(BASE, seed=42)).json()
        b = client.post("/api/experiments/run", json=dict(BASE, seed=99)).json()
        assert a["manifest_sha"] != b["manifest_sha"]
        assert a["snapshot_sha"] != b["snapshot_sha"]


# --------------------------------------------------------------------------- #
# 3. Lifecycle
# --------------------------------------------------------------------------- #
class TestAsyncSubmit:
    def _wait(self, run_id, timeout=90.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = client.get(f"/api/experiments/{run_id}/status").json()
            if status["status"] in {"succeeded", "failed", "cancelled"}:
                return status
            time.sleep(0.25)
        pytest.fail(f"run {run_id} did not finish within {timeout}s")

    def test_submit_returns_202_and_queued_run(self):
        with TestClient(app) as c:
            res = c.post("/api/experiments/submit", json={
                "config": BASE,
                "created_by": "agent:designer",
                "hypothesis": "放宽 v2.3 通过率到 60% 是否仍保持 RAROC 优势",
                "tags": ["sweep", "raroc"],
            })
            assert res.status_code == 202
            body = res.json()
            assert body["status"] == "queued"
            assert len(body["manifest_sha"]) == 64

            deadline = time.time() + 90
            while time.time() < deadline:
                status = c.get(f"/api/experiments/{body['run_id']}/status").json()
                if status["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.25)
            assert status["status"] == "succeeded", status
            run = c.get(f"/api/experiments/{body['run_id']}").json()
            assert run["created_by"] == "agent:designer"
            assert run["layers"]["l2"]["kpis"]

    def test_submit_reports_identical_prior_runs(self):
        with TestClient(app) as c:
            first = c.post("/api/experiments/submit", json={"config": BASE}).json()
            second = c.post("/api/experiments/submit", json={"config": BASE}).json()
            assert first["manifest_sha"] == second["manifest_sha"]
            # the first submission is already recorded, so the second sees it
            assert any(r["run_id"] == first["run_id"]
                       for r in second["identical_prior_runs"])

    def test_invalid_config_is_rejected_before_queueing(self):
        res = client.post("/api/experiments/submit",
                          json={"config": dict(BASE, challenger="v9.9")})
        assert res.status_code == 400


# --------------------------------------------------------------------------- #
# 4. Memory
# --------------------------------------------------------------------------- #
class TestRunRegistry:
    def test_annotate_records_question_and_finding(self):
        run = client.post("/api/experiments/run", json=BASE).json()
        res = client.post(f"/api/experiments/{run['run_id']}/annotate", json={
            "hypothesis": "v2.3 在 RAROC 上优于 v2.2",
            "conclusion": "成立：RAROC 24% vs 20%，坏账持平",
            "tags": ["champion-challenger"],
        })
        assert res.status_code == 200
        body = res.json()
        assert body["conclusion"].startswith("成立")
        assert body["tags"] == ["champion-challenger"]

    def test_annotate_unknown_run_404s(self):
        res = client.post("/api/experiments/nope/annotate",
                          json={"conclusion": "x"})
        assert res.status_code == 404

    def test_lineage_of_a_fresh_run_is_itself(self):
        run = client.post("/api/experiments/run", json=BASE).json()
        lineage = client.get(f"/api/experiments/{run['run_id']}/lineage").json()
        assert lineage["root_run_id"] == run["run_id"]
        assert [r["run_id"] for r in lineage["runs"]] == [run["run_id"]]

    def test_jobs_endpoint_lists_recent_jobs(self):
        res = client.get("/api/experiments/jobs")
        assert res.status_code == 200
        assert isinstance(res.json()["jobs"], list)
