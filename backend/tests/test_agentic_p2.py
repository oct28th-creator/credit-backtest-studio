"""P2 agent layer: tools, guardrails, budgets, and the investigation loop.

The loop is exercised with no API key configured, so these tests cover the
deterministic path end to end: plan → run → guardrails → findings → critique →
annotation. What an LLM changes is the *quality* of the plan and the prose,
never the mechanics asserted here.
"""
import pytest
from fastapi.testclient import TestClient

from app.agent import budget as budget_mod
from app.agent import guardrails, tools
from app.main import app

client = TestClient(app)

BASE = {
    "champion": "v2.2",
    "challenger": "v2.3",
    "beta": None,
    "sample_id": "consumer_2024q1q2",
    "language": "zh",
}


def _tool(name, args=None, session_id=None, expect=200):
    body = {"args": args or {}}
    if session_id:
        body["session_id"] = session_id
    res = client.post(f"/api/agent/tools/{name}", json=body)
    assert res.status_code == expect, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# Tool surface
# --------------------------------------------------------------------------- #
class TestToolSurface:
    def test_registry_is_self_describing(self):
        listed = client.get("/api/agent/tools").json()["tools"]
        names = {t["name"] for t in listed}
        assert {"submit_experiment", "sensitivity_scan", "compare_runs",
                "search_experiments", "check_guardrails", "annotate_run"} <= names
        for t in listed:
            assert t["input_schema"]["type"] == "object"
        # the tools that cost compute are flagged, so a caller can budget them
        spending = {t["name"] for t in listed if t["spends_compute"]}
        assert spending == {"submit_experiment", "sensitivity_scan"}

    def test_unknown_tool_is_rejected(self):
        _tool("delete_everything", expect=400)

    def test_missing_and_unknown_arguments_are_rejected(self):
        _tool("get_metrics", {}, expect=400)
        _tool("get_metrics", {"run_id": "x", "nope": 1}, expect=400)

    def test_catalogue_exposes_overridable_knobs(self):
        out = _tool("list_strategies")["result"]
        assert out["builtin"]
        assert "target_approval_rate" in out["builtin"][0]["knobs"]

    def test_submit_returns_compact_metrics_not_chart_payloads(self):
        out = _tool("submit_experiment", {"config": BASE})["result"]
        metrics = out["metrics"]
        assert set(metrics["strategies"]) == {"v2.2", "v2.3"}
        chall = metrics["strategies"]["v2.3"]
        assert chall["approval_rate"] is not None and chall["raroc"] is not None
        # no chart series leaked into the agent-facing payload
        blob = str(metrics)
        assert "roc_curve" not in blob and "calibration" not in blob
        assert "vintage" not in blob and "pareto" not in blob
        assert len(blob) < 4000, "compact metrics must stay small enough to reason over"

    def test_identical_experiment_is_reused_not_recomputed(self):
        first = _tool("submit_experiment", {"config": BASE})["result"]
        second = _tool("submit_experiment", {"config": BASE})["result"]
        assert second["cached"] is True
        assert second["run_id"] == first["run_id"]

    def test_search_finds_annotated_prior_work(self):
        run = _tool("submit_experiment", {"config": BASE})["result"]
        _tool("annotate_run", {"run_id": run["run_id"],
                               "conclusion": "唯一标记 zzsearchzz",
                               "tags": ["p2-test"]})
        hits = _tool("search_experiments", {"query": "zzsearchzz"})["result"]["runs"]
        assert any(h["run_id"] == run["run_id"] for h in hits)
        by_tag = _tool("search_experiments", {"tag": "p2-test"})["result"]["runs"]
        assert by_tag


class TestSensitivityScan:
    def test_sweep_expands_server_side_and_moves_approval(self):
        out = _tool("sensitivity_scan", {
            "base_config": BASE, "strategy": "v2.3",
            "knob": "target_approval_rate", "values": [0.30, 0.60],
        })["result"]
        assert len(out["points"]) == 2
        low, high = out["points"]
        apr = lambda p: p["metrics"]["strategies"]["v2.3"]["approval_rate"]  # noqa: E731
        assert apr(low) < apr(high)
        # each point is an independently citable run
        assert low["run_id"] != high["run_id"]

    def test_non_overridable_knob_is_refused(self):
        _tool("sensitivity_scan", {
            "base_config": BASE, "strategy": "v2.3",
            "knob": "bad_rate", "values": [0.1],
        }, expect=400)

    def test_sweep_width_is_capped(self):
        _tool("sensitivity_scan", {
            "base_config": BASE, "strategy": "v2.3", "knob": "dti_limit",
            "values": [0.5] * 13,
        }, expect=400)


# --------------------------------------------------------------------------- #
# Guardrails — deterministic, and not overridable by narrative
# --------------------------------------------------------------------------- #
def _run(di=0.95, approval=0.44, bad=0.017, auc=0.78, p_value=0.01, n=80000):
    return {
        "run_id": "r1", "champion": "v2.2", "challenger": "v2.3", "beta": None,
        "sample_size": n, "config": {},
        "layers": {
            "l1": {"kpis": [{"version": "v2.3", "auc": auc, "ks": 0.4}]},
            "l2": {"kpis": [{"version": "v2.3", "approval_rate": approval,
                             "el": bad, "raroc": 0.24, "avg_profit": 300}]},
            "l3": {"kpis": [{"version": "v2.3", "m12_bad": bad, "fpd": 0.004}]},
            "l4": {"matrices": {"v2.3": {"p_value": p_value,
                                         "swap_in": {"count": 100, "bad_rate": 0.02},
                                         "swap_out": {"count": 80, "bad_rate": 0.03}}}},
            "l5": {"kpis": {"tpr_gap": 0.02}, "di_by_group": {"v2.3": {"female_male": di}}},
        },
    }


class TestGuardrails:
    def test_clean_run_passes(self):
        report = guardrails.check_run(_run())
        assert report["ok"] and not report["blocking"]

    def test_disparate_impact_below_four_fifths_blocks(self):
        report = guardrails.check_run(_run(di=0.61))
        assert not report["ok"]
        assert report["blocking"][0]["code"] == "disparate_impact"

    def test_tiny_approved_book_blocks(self):
        report = guardrails.check_run(_run(approval=0.001, n=10000))
        assert any(b["code"] == "approved_book_too_small" for b in report["blocking"])

    def test_insignificant_swap_set_warns(self):
        report = guardrails.check_run(_run(p_value=0.42))
        assert report["ok"]  # not blocking
        assert any(w["code"] == "swap_not_significant" for w in report["warnings"])

    def test_extreme_override_warns(self):
        run = _run()
        run["config"] = {"policy_overrides": {"v2.3": {"target_approval_rate": 0.98}}}
        report = guardrails.check_run(run)
        assert any(w["code"] == "extreme_override" for w in report["warnings"])

    def test_summarize_folds_a_batch(self):
        summary = guardrails.summarize([guardrails.check_run(_run()),
                                        guardrails.check_run(_run(di=0.5))])
        assert summary["n_runs_checked"] == 2
        assert summary["n_blocking"] == 1 and summary["ok"] is False

    def test_guardrail_tool_runs_on_a_real_run(self):
        run = _tool("submit_experiment", {"config": BASE})["result"]
        report = _tool("check_guardrails", {"run_id": run["run_id"]})["result"]
        assert set(report) >= {"ok", "blocking", "warnings", "thresholds"}


# --------------------------------------------------------------------------- #
# Budgets — enforced in the tool layer, not in the prompt
# --------------------------------------------------------------------------- #
class TestBudget:
    def test_budget_is_clamped_to_platform_limits(self):
        b = budget_mod.Budget(max_experiments=9999, max_wall_seconds=1).clamp()
        assert b.max_experiments == 40 and b.max_wall_seconds == 30

    def test_experiment_budget_stops_the_second_call(self):
        session = client.post("/api/agent/sessions", json={
            "goal": "budget test", "budget": {"max_experiments": 1},
        }).json()
        sid = session["session_id"]
        _tool("submit_experiment",
              {"config": {**BASE, "seed": 4242}, "reuse_identical": False}, session_id=sid)
        _tool("submit_experiment",
              {"config": {**BASE, "seed": 4343}, "reuse_identical": False},
              session_id=sid, expect=429)
        after = client.get(f"/api/agent/sessions/{sid}").json()
        assert after["experiments_spent"] == 1
        assert after["status"] == "budget_exhausted"

    def test_cached_reuse_does_not_spend_budget(self):
        client.post("/api/experiments/run", json=BASE)  # ensure it exists
        session = client.post("/api/agent/sessions", json={
            "goal": "cache test", "budget": {"max_experiments": 1},
        }).json()
        sid = session["session_id"]
        out = _tool("submit_experiment", {"config": BASE}, session_id=sid)["result"]
        assert out["cached"] is True
        assert client.get(f"/api/agent/sessions/{sid}").json()["experiments_spent"] == 0

    def test_unknown_session_is_404(self):
        res = client.post("/api/agent/tools/list_strategies",
                          json={"args": {}, "session_id": "nope"})
        assert res.status_code == 404


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
class TestInvestigationLoop:
    @pytest.fixture(scope="class")
    def investigation(self):
        res = client.post("/api/agent/investigate", json={
            "goal": "v2.3 放宽通过率后 RAROC 是否还优于 v2.2",
            "base_config": BASE,
            "budget": {"max_experiments": 3},
        })
        assert res.status_code == 200, res.text
        return res.json()

    def test_phases_run_in_order(self, investigation):
        phases = [e["phase"] for e in investigation["events"]]
        for expected in ["session", "prior_work", "plan", "guardrails",
                         "comparison", "findings", "critique", "done"]:
            assert expected in phases, phases
        assert phases.index("plan") < phases.index("guardrails") < phases.index("findings")
        # guardrails are computed before any narrative is produced
        assert phases.index("guardrails") < phases.index("critique")

    def test_plan_respects_the_budget(self, investigation):
        plan = next(e for e in investigation["events"] if e["phase"] == "plan")["plan"]
        assert 1 <= len(plan["experiments"]) <= 3
        assert plan["hypothesis"]

    def test_every_run_is_real_and_citable(self, investigation):
        done = investigation["result"]
        assert done["status"] == "completed"
        assert done["run_ids"]
        for rid in done["run_ids"]:
            stored = client.get(f"/api/experiments/{rid}").json()
            assert stored["layers"]["l2"]["kpis"]
            assert len(stored["manifest_sha"]) == 64

    def test_findings_and_critique_are_structured(self, investigation):
        findings = next(e for e in investigation["events"]
                        if e["phase"] == "findings")["findings"]
        critique = next(e for e in investigation["events"]
                        if e["phase"] == "critique")["critique"]
        assert findings["findings"]
        assert critique["verdict"] in {"supported", "partially_supported",
                                       "not_supported", "inconclusive"}
        assert critique["issues"]

    def test_critic_flags_the_environment_limit(self, investigation):
        critique = next(e for e in investigation["events"]
                        if e["phase"] == "critique")["critique"]
        text = str(critique)
        assert "回放" in text or "拒绝推断" in text or "seed" in text

    def test_conclusion_is_written_back_to_the_registry(self, investigation):
        rid = investigation["result"]["run_ids"][0]
        lineage_hit = client.post(f"/api/experiments/{rid}/annotate",
                                  json={"tags": ["verify"]}).json()
        assert lineage_hit["conclusion"], "the agent must record what it concluded"
        assert lineage_hit["conclusion"].startswith("[")

    def test_session_accounting_matches_the_runs(self, investigation):
        session = investigation["session"]
        produced = len(session["run_ids"]) + len(session["cached_run_ids"])
        assert produced == len(investigation["result"]["run_ids"])
        assert session["experiments_spent"] <= session["budget"]["max_experiments"]


class TestBlockingGuardrailOverridesTheNarrative:
    def test_blocking_finding_forces_not_supported(self):
        from app.agent import orchestrator

        report = {"n_blocking": 1, "blocking": [{"detail": "DI 0.5", "severity": "block"}],
                  "warnings": [], "ok": False}
        out = orchestrator._fallback_critique(report, n_experiments=3)
        out = {**out, "verdict": "supported", "confidence": 0.95}
        # the deterministic override lives in _critique; emulate its contract
        assert report["n_blocking"]
        import asyncio

        session = budget_mod.create(goal="x")
        merged = asyncio.run(orchestrator._critique(
            {"hypothesis": "h"}, {"rows": []}, {"findings": []}, report, 3, session))
        assert merged["verdict"] == "not_supported"
        assert merged["confidence"] <= 0.3
