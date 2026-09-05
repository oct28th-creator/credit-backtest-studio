"""P3 simulation environments: reject inference, its error bar, and replication.

The value here is not that the platform can estimate hidden outcomes — every
credit shop does that. It is that the estimate arrives with a measured error,
because the environment hides labels it can check itself against, and the
guardrails refuse a conclusion whose method is less accurate than the effect
it claims.
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.agent import guardrails
from app.data.fixtures import _approve_mask, _model_score, generate_synthetic_data
from app.envs import get_environment, list_environments
from app.envs import reject_inference as ri
from app.envs import replication
from app.main import app

client = TestClient(app)

BASE = {"champion": "v2.2", "challenger": "v2.3", "beta": None,
        "sample_id": "consumer_2024q1q2", "language": "zh"}


def _tool(name, args=None, expect=200):
    res = client.post(f"/api/agent/tools/{name}", json={"args": args or {}})
    assert res.status_code == expect, res.text
    return res.json()


@pytest.fixture(scope="module")
def book():
    df = generate_synthetic_data(n=20000, seed=42)
    champ = _approve_mask(df, "v2.2")
    masks = {"v2.3": _approve_mask(df, "v2.3"), "v2.4-Beta": _approve_mask(df, "v2.4-Beta")}
    pd_hats = {sid: _model_score(df, sid) for sid in ["v2.2", "v2.3", "v2.4-Beta"]}
    return df, champ, masks, pd_hats


# --------------------------------------------------------------------------- #
# Environment registry
# --------------------------------------------------------------------------- #
class TestEnvironments:
    def test_every_environment_states_what_it_cannot_answer(self):
        envs = list_environments()
        assert envs
        for e in envs:
            assert e["not_valid_for"], f"{e['id']} must declare its limits"
            assert e["confidence"] in {"high", "medium", "low"}

    def test_unknown_environment_falls_back_to_replay(self):
        assert get_environment("does-not-exist").id == "replay"
        assert get_environment(None).id == "replay"

    def test_replay_run_carries_its_environment_and_limits(self):
        run = client.post("/api/experiments/run", json=BASE).json()
        env = run["environment"]
        assert env["id"] == "replay" and env["level"] == "L0a"
        assert any("拒绝" in x or "行为" in x for x in env["not_valid_for"])

    def test_environment_is_part_of_run_identity(self):
        a = client.post("/api/experiments/run", json=BASE).json()
        b = client.post("/api/experiments/run",
                        json={**BASE, "env_id": "reject_inference"}).json()
        assert a["manifest_sha"] != b["manifest_sha"], \
            "changing the assumed world must change the run's identity"

    def test_tool_lists_environments(self):
        out = _tool("list_environments")["result"]["environments"]
        assert {e["id"] for e in out} >= {"replay", "reject_inference"}


# --------------------------------------------------------------------------- #
# Reject inference
# --------------------------------------------------------------------------- #
class TestRejectInference:
    def test_none_mode_is_the_biased_baseline(self, book):
        df, champ, masks, pd_hats = book
        report = ri.report(df, champ, masks, pd_hats, mode="none")
        s = report["strategies"]["v2.3"]
        assert s["estimated_bad_rate"] == 0.0
        assert s["direction"] == "低估"
        # ignoring rejects understates swap-in risk by the whole true rate
        assert s["bias_pp"] == pytest.approx(-s["oracle_bad_rate"] * 100, abs=0.01)

    @pytest.mark.parametrize("mode", ["parceling", "fuzzy", "augmentation"])
    def test_every_method_reports_its_own_error(self, book, mode):
        df, champ, masks, pd_hats = book
        report = ri.report(df, champ, masks, pd_hats, mode=mode)
        s = report["strategies"]["v2.3"]
        assert s["n_swap_in"] > 0
        assert 0.0 <= s["estimated_bad_rate"] <= 1.0
        assert s["oracle_bad_rate"] > 0
        assert s["relative_error"] is not None
        assert report["max_relative_error"] is not None

    def test_estimating_only_the_masked_population(self, book):
        df, champ, masks, pd_hats = book
        report = ri.report(df, champ, masks, pd_hats)
        assert report["n_observed"] + report["n_masked"] == len(df)
        # the swap-in set is by construction inside the masked population
        assert report["strategies"]["v2.3"]["n_swap_in"] <= report["n_masked"]

    def test_unknown_mode_is_rejected(self, book):
        df, champ, masks, pd_hats = book
        with pytest.raises(ValueError, match="unknown ri_mode"):
            ri.estimate_bad(df, champ, masks["v2.3"], pd_hats["v2.3"], mode="wishful")

    def test_compare_modes_ranks_by_measured_error(self, book):
        df, champ, masks, pd_hats = book
        out = ri.compare_modes(df, champ, masks, pd_hats)
        assert set(out["modes"]) == set(ri.MODES)
        errors = [r["max_relative_error"] for r in out["ranked"]
                  if r["max_relative_error"] is not None]
        assert errors == sorted(errors), "ranked worst-last by measured error"

    def test_ri_run_attaches_the_report_to_the_run(self):
        run = client.post("/api/experiments/run",
                          json={**BASE, "env_id": "reject_inference",
                                "ri_mode": "fuzzy"}).json()
        report = run["environment"]["reject_inference"]
        assert report["mode"] == "fuzzy"
        assert report["strategies"]["v2.3"]["oracle_bad_rate"] > 0
        assert "oracle" in report["note"]

    def test_compare_ri_modes_tool_picks_a_best_method(self):
        out = _tool("compare_ri_modes", {"config": BASE})["result"]
        assert out["best_mode"] in ri.MODES
        assert out["modes"][out["best_mode"]]["max_relative_error"] is not None


# --------------------------------------------------------------------------- #
# Replication across seeds
# --------------------------------------------------------------------------- #
def _compact(raroc_by_strategy, seed=1):
    return {"seed": seed,
            "strategies": {sid: {"raroc": v, "approval_rate": 0.4, "bad_rate": 0.02,
                                 "auc": 0.7, "ks": 0.3}
                           for sid, v in raroc_by_strategy.items()}}


class TestReplication:
    def test_consistent_ranking_is_reported_stable(self):
        out = replication.aggregate(
            [_compact({"v2.2": 0.20, "v2.3": 0.24}),
             _compact({"v2.2": 0.19, "v2.3": 0.25}),
             _compact({"v2.2": 0.21, "v2.3": 0.23})], seeds=[1, 2, 3])
        assert out["stable"] is True
        assert out["ranking_by_raroc"]["winner"] == "v2.3"
        assert out["strategies"]["v2.3"]["raroc"]["ci95"] is not None

    def test_flipped_ranking_is_reported_unstable(self):
        out = replication.aggregate(
            [_compact({"v2.2": 0.20, "v2.3": 0.24}),
             _compact({"v2.2": 0.26, "v2.3": 0.22})], seeds=[1, 2])
        assert out["stable"] is False
        assert "翻转" in out["verdict"] or "噪声" in out["verdict"]

    def test_seeds_are_distinct_and_bounded(self):
        seeds = replication.build_seeds(42, 5)
        assert len(seeds) == len(set(seeds)) == 5
        assert len(replication.build_seeds(42, 99)) <= 8

    def test_replicate_tool_runs_real_backtests(self):
        out = _tool("replicate_across_seeds", {"config": BASE, "n": 2})["result"]
        assert out["n"] == 2
        assert out["strategies"]["v2.3"]["approval_rate"]["n"] == 2
        assert out["stable"] in (True, False)


# --------------------------------------------------------------------------- #
# Guardrails become environment-aware
# --------------------------------------------------------------------------- #
def _run_with_env(env):
    return {
        "run_id": "r1", "champion": "v2.2", "challenger": "v2.3", "beta": None,
        "sample_size": 80000, "config": {}, "environment": env,
        "layers": {
            "l1": {"kpis": [{"version": "v2.3", "auc": 0.78}]},
            "l2": {"kpis": [{"version": "v2.3", "approval_rate": 0.44, "el": 0.017,
                             "raroc": 0.24, "avg_profit": 300}]},
            "l3": {"kpis": []}, "l4": {"matrices": {}},
            "l5": {"kpis": {}, "di_by_group": {}},
        },
    }


class TestEnvironmentGuardrails:
    def test_replay_environment_always_carries_its_caveat(self):
        report = guardrails.check_run(_run_with_env({"id": "replay", "level": "L0a"}))
        assert any(w["code"] == "replay_only_environment" for w in report["warnings"])

    def test_unreliable_reject_inference_blocks_the_conclusion(self):
        env = {"id": "reject_inference", "level": "L0b",
               "reject_inference": {"mode": "parceling", "max_relative_error": 0.83}}
        report = guardrails.check_run(_run_with_env(env))
        assert not report["ok"]
        assert report["blocking"][0]["code"] == "reject_inference_unreliable"

    def test_moderate_error_warns_instead_of_blocking(self):
        env = {"id": "reject_inference", "level": "L0b",
               "reject_inference": {"mode": "fuzzy", "max_relative_error": 0.30}}
        report = guardrails.check_run(_run_with_env(env))
        assert report["ok"]
        assert any(w["code"] == "reject_inference_noisy" for w in report["warnings"])

    def test_accurate_method_passes_clean(self):
        env = {"id": "reject_inference", "level": "L0b",
               "reject_inference": {"mode": "fuzzy", "max_relative_error": 0.05}}
        report = guardrails.check_run(_run_with_env(env))
        assert report["ok"] and not report["warnings"]


# --------------------------------------------------------------------------- #
# The loop now settles the sampling question before concluding
# --------------------------------------------------------------------------- #
class TestLoopWithReplication:
    def test_investigation_replicates_the_winner(self):
        res = client.post("/api/agent/investigate", json={
            "goal": "v2.3 的 RAROC 优势是否稳健",
            "base_config": BASE,
            "budget": {"max_experiments": 5},
        }).json()
        phases = [e["phase"] for e in res["events"]]
        assert "replication" in phases
        rep = next(e for e in res["events"] if e["phase"] == "replication")["replication"]
        if rep:  # skipped only when the budget ran out first
            assert rep["n"] >= 2
            assert phases.index("replication") < phases.index("critique")

    def test_unstable_ranking_forces_not_supported(self):
        import asyncio

        from app.agent import budget as budget_mod
        from app.agent import orchestrator

        unstable = {"stable": False, "verdict": "排序在不同随机种子下发生翻转", "n": 3}
        clean_report = {"n_blocking": 0, "blocking": [], "warnings": [], "ok": True}
        out = asyncio.run(orchestrator._critique(
            {"hypothesis": "h"}, {"rows": []}, {"findings": []},
            clean_report, 3, budget_mod.create(goal="x"), unstable))
        assert out["verdict"] == "not_supported"
        assert out["confidence"] <= 0.25
