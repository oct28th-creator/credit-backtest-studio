"""P5: deterministic conclusions — gain decomposition, guardrail repair, evidence bundles.

The common thread: each of these is a sentence a person would otherwise ask a
model to write, computed instead from the numbers. The model's remaining job
is to say it in prose, which is the only part it can be trusted with.
"""
import pytest
from fastapi.testclient import TestClient

from app.agent import insights
from app.main import app

client = TestClient(app)

BASE = {"champion": "v2.2", "challenger": "v2.3", "beta": None,
        "sample_id": "consumer_2024q1q2", "language": "zh"}


def _tool(name, args=None, expect=200):
    res = client.post(f"/api/agent/tools/{name}", json={"args": args or {}})
    assert res.status_code == expect, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# L2 absolute scale
# --------------------------------------------------------------------------- #
class TestPortfolioTotals:
    @pytest.fixture(scope="class")
    def run(self):
        return client.post("/api/experiments/run", json=BASE).json()

    def test_totals_accompany_the_rates(self, run):
        for k in run["layers"]["l2"]["kpis"]:
            assert k["n_approved"] > 0
            assert k["total_balance"] > 0
            assert k["economic_capital"] > 0

    def test_totals_are_consistent_with_the_rate(self, run):
        k = next(x for x in run["layers"]["l2"]["kpis"] if x["version"] == "v2.3")
        assert k["n_approved"] == pytest.approx(k["approval_rate"] * run["sample_size"], rel=0.01)

    def test_a_higher_approval_strategy_books_more_balance(self, run):
        champ = next(k for k in run["layers"]["l2"]["kpis"] if k["version"] == "v2.2")
        chall = next(k for k in run["layers"]["l2"]["kpis"] if k["version"] == "v2.3")
        assert chall["total_balance"] > champ["total_balance"]

    def test_reason_coverage_sits_with_the_reasons_it_describes(self, run):
        k = next(x for x in run["layers"]["l2"]["kpis"] if x["version"] == "v2.3")
        assert 0 <= k["reason_coverage"] <= 1
        # kept in L5 one more release for older clients, but marked as moved
        assert run["layers"]["l5"]["kpis"]["reason_coverage_moved_to"] == "l2"

    def test_score_bands_report_what_disagreement_costs(self, run):
        bands = run["layers"]["l4"]["matrices"]["v2.3"]["consistency_by_band"]
        assert bands
        assert any(b["swap_in_n"] for b in bands)
        for b in bands:
            if b["swap_in_n"]:
                assert 0 <= b["swap_in_bad_rate"] <= 1


# --------------------------------------------------------------------------- #
# Gain decomposition
# --------------------------------------------------------------------------- #
def _matrix(model_n, policy_n, si_bad=0.023, so_bad=0.052):
    return {
        "swap_in": {"count": model_n + policy_n, "bad_rate": si_bad},
        "swap_out": {"count": 2800, "bad_rate": so_bad},
        "swap_in_raroc": 0.236,
        "swap_in_attribution": [
            {"reason": "风险评分不足", "rule": "pd_hat > 0.01", "n": model_n, "pct": 0.8, "bad_rate": 0.023},
            {"reason": "近期逾期记录", "rule": "months_clean < 12", "n": policy_n, "pct": 0.2, "bad_rate": 0.018},
        ],
    }


class TestGainDecomposition:
    def test_model_driven_gain_is_named_as_such(self):
        out = insights.decompose_swap(_matrix(16000, 3000))
        assert out["driver"] == "model"
        assert out["model_driven"]["share"] > 0.8
        assert "模型区分度提升" in out["headline"]
        assert "按模型升级审批" in out["headline"]

    def test_policy_driven_gain_is_named_as_such(self):
        out = insights.decompose_swap(_matrix(2000, 17000))
        assert out["driver"] == "policy"
        assert "政策放松" in out["headline"]

    def test_mixed_gain_refuses_to_pick_a_side(self):
        out = insights.decompose_swap(_matrix(10000, 9000))
        assert out["driver"] == "mixed"
        assert "都不占主导" in out["headline"]

    def test_headline_states_the_swap_quality_comparison(self):
        out = insights.decompose_swap(_matrix(16000, 3000, si_bad=0.023, so_bad=0.052))
        assert "多批的比拒掉的更干净" in out["headline"]
        worse = insights.decompose_swap(_matrix(16000, 3000, si_bad=0.06, so_bad=0.02))
        assert "多批的比拒掉的更干净" not in worse["headline"]

    def test_shares_and_counts_agree(self):
        out = insights.decompose_swap(_matrix(16000, 4000))
        assert out["total_swap_in"] == 20000
        assert out["model_driven"]["n"] + out["policy_driven"]["n"] + out["other_n"] == 20000
        assert out["model_driven"]["share"] == pytest.approx(0.8, abs=0.001)

    def test_empty_attribution_yields_nothing_rather_than_a_guess(self):
        assert insights.decompose_swap({"swap_in_attribution": []}) is None

    def test_endpoint_decomposes_a_real_run(self):
        run = client.post("/api/experiments/run", json=BASE).json()
        out = client.get(f"/api/experiments/{run['run_id']}/decomposition").json()
        assert out["driver"] in {"model", "policy", "mixed"}
        assert out["headline"]
        # on the default book the gain is overwhelmingly model-driven
        assert out["model_driven"]["share"] > 0.6

    def test_tool_matches_the_endpoint(self):
        run = client.post("/api/experiments/run", json=BASE).json()
        viaapi = client.get(f"/api/experiments/{run['run_id']}/decomposition").json()
        viatool = _tool("decompose_gain", {"run_id": run["run_id"]})["result"]
        assert viatool["headline"] == viaapi["headline"]


# --------------------------------------------------------------------------- #
# Guardrail repair
# --------------------------------------------------------------------------- #
class TestGuardrailRepair:
    def test_candidates_walk_outward_from_the_current_value(self):
        plan = insights.repair_candidates("bad_rate_ceiling", 0.44)
        assert plan["knob"] == "target_approval_rate"
        assert plan["values"][0] < 0.44, "tightening is the direction of relief"
        gaps = [abs(v - 0.44) for v in plan["values"]]
        assert gaps == sorted(gaps), "nearest first: smallest change that works"

    def test_unknown_finding_has_no_automatic_repair(self):
        assert insights.repair_candidates("protected_attribute_as_input", 0.4) is None

    def test_clean_run_needs_no_repair(self):
        run = client.post("/api/experiments/run", json=BASE).json()
        out = _tool("find_fix", {"run_id": run["run_id"], "code": "replay_only_environment"})["result"]
        # replay warning has no knob; the tool says so instead of sweeping
        assert out["fixed"] is None

    def test_structural_fairness_problem_is_diagnosed_not_papered_over(self):
        """v2.4-Beta's DI gap comes from its thin-file gate, so no approval-rate
        setting can clear it. The useful output is that sentence, not a sweep
        that quietly returns nothing."""
        run = client.post("/api/experiments/run",
                          json={**BASE, "challenger": "v2.4-Beta"}).json()
        out = _tool("find_fix", {"run_id": run["run_id"], "code": "disparate_impact"})["result"]
        assert out["finding"]["strategy"] == "v2.4-Beta", "repair targets the strategy under test"
        assert out["fixed"] is None
        assert "不是阈值问题" in out["note"]
        assert out["diagnosis"]["dominant_reason"] == "薄文件/行为不足"
        assert out["diagnosis"]["by_reason"][0]["gap_pp"] > 50

    def test_attempts_are_real_citable_runs(self):
        run = client.post("/api/experiments/run",
                          json={**BASE, "challenger": "v2.4-Beta"}).json()
        out = _tool("find_fix", {"run_id": run["run_id"], "code": "disparate_impact"})["result"]
        assert out["attempts"]
        for a in out["attempts"][:2]:
            stored = client.get(f"/api/experiments/{a['run_id']}").json()
            assert stored["layers"]["l2"]["kpis"]


# --------------------------------------------------------------------------- #
# Evidence bundle
# --------------------------------------------------------------------------- #
class TestEvidenceBundle:
    @pytest.fixture(scope="class")
    def bundle(self):
        run = client.post("/api/experiments/run", json=BASE).json()
        res = client.get(f"/api/experiments/{run['run_id']}/bundle")
        assert res.status_code == 200, res.text
        return res.json()

    def test_it_takes_a_position(self, bundle):
        assert bundle["recommendation"]["verdict"] in {
            "不可推进", "证据不足", "可提交人工评审"}
        assert bundle["recommendation"]["why"]

    def test_without_replication_it_says_the_evidence_is_incomplete(self, bundle):
        assert bundle["replication_included"] is False
        assert any("多种子" in q for q in bundle["open_questions"])

    def test_recommendation_precedence(self):
        """Blocking beats everything; a flipped ranking beats a clean sheet;
        a missing replication is never "ready for review"."""
        from app.agent import bundle as bundle_mod

        clean = {"blocking": [], "warnings": []}
        env = {"id": "replay", "level": "L0a", "not_valid_for": ["行为反馈"]}

        blocked = bundle_mod._recommendation(
            {"blocking": [{"detail": "DI 0.6"}], "warnings": []},
            {"stable": True}, env)
        assert blocked["verdict"] == "不可推进"

        flipped = bundle_mod._recommendation(clean, {"stable": False}, env)
        assert flipped["verdict"] == "不可推进"
        assert "抽样" in flipped["why"]

        unreplicated = bundle_mod._recommendation(clean, None, env)
        assert unreplicated["verdict"] == "证据不足"

        ready = bundle_mod._recommendation(clean, {"stable": True}, env)
        assert ready["verdict"] == "可提交人工评审"
        assert "不覆盖" in ready["note"]

    def test_the_incumbent_champions_own_fairness_gap_is_surfaced(self, bundle):
        """On the default book v2.2 itself sits at DI 0.796 for 18-25s. A pack
        that recommended shipping past that would be the whole problem."""
        assert bundle["recommendation"]["verdict"] == "不可推进"
        assert "disparate_impact" in bundle["markdown"]

    def test_it_lists_what_it_does_not_answer(self, bundle):
        qs = bundle["open_questions"]
        assert qs
        assert any("行为反馈" in q for q in qs)
        assert any("回放" in q for q in qs)

    def test_the_document_carries_the_evidence_chain(self, bundle):
        md = bundle["markdown"]
        for section in ["## 1. 实验配置", "## 2. 核心指标", "## 3. 增量来源分解",
                        "## 4. 红线检查", "## 5. 稳健性", "## 7. 本材料未回答的问题",
                        "## 8. 证据链"]:
            assert section in md, f"missing {section}"
        assert "复现哈希" in md
        assert "上线决策由人做出" in md

    def test_a_blocked_run_cannot_be_recommended(self):
        run = client.post("/api/experiments/run",
                          json={**BASE, "challenger": "v2.4-Beta"}).json()
        out = client.get(f"/api/experiments/{run['run_id']}/bundle").json()
        assert out["recommendation"]["verdict"] == "不可推进"
        assert "阻断" in out["recommendation"]["why"]

    def test_bundle_of_unknown_run_is_404(self):
        assert client.get("/api/experiments/nope/bundle").status_code == 404


# --------------------------------------------------------------------------- #
# Critic is armed with the RI method comparison
# --------------------------------------------------------------------------- #
class TestCriticUsesRiComparison:
    def test_fallback_critic_reports_the_best_method(self):
        from app.agent import orchestrator

        ri = {"best_mode": "fuzzy",
              "ranked": [{"mode": "parceling", "max_relative_error": 0.83},
                         {"mode": "fuzzy", "max_relative_error": 0.09}]}
        out = orchestrator._fallback_critique(
            {"n_blocking": 0, "blocking": [], "warnings": []}, 3, None, ri)
        text = str(out["issues"])
        assert "fuzzy" in text and "0.83" in text

    def test_investigation_compares_methods_under_reject_inference(self):
        res = client.post("/api/agent/investigate", json={
            "goal": "拒绝推断下 v2.3 的 swap-in 风险估计可信吗",
            "base_config": {**BASE, "env_id": "reject_inference", "ri_mode": "parceling"},
            "budget": {"max_experiments": 3},
        }).json()
        phases = [e["phase"] for e in res["events"]]
        assert "ri_comparison" in phases
        cmp_event = next(e for e in res["events"] if e["phase"] == "ri_comparison")
        assert cmp_event["ri_comparison"]["best_mode"]
        assert phases.index("ri_comparison") < phases.index("critique")
