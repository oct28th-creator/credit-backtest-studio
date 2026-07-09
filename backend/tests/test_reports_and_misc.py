"""Tests for the static report builder, app lifespan, and stability service.

_build_static_report is unit-tested with the raw layer format it was written
against (per-strategy keys + _summary + _swap_chall_vs_champ). Note that runs
stored by /api/experiments/run hold the *reshaped* frontend layer format, so
via the API these sections render empty — these tests pin down the builder's
own contract.
"""
from fastapi.testclient import TestClient

from app.api.reports import _build_static_report
from app.main import app
from app.services import stability


# ---------------------------------------------------------------------------
# _build_static_report
# ---------------------------------------------------------------------------

def _raw_run(beta=True, beta_compliant=True):
    def _summary_row(sid, issue=False):
        return {
            "strategy_id": sid, "strategy_name": sid,
            "approval_rate": 0.28, "bad_rate": 0.018, "raroc": 0.18,
            "avg_profit": 310.0, "auc": 0.78, "ks": 0.42, "fpd_rate": 0.006,
            "has_compliance_issue": issue,
        }

    def _strategy_layers(compliant=True):
        return {
            "l3": {
                "mob12_bad_rate": 0.018, "fpd_rate": 0.006,
                "roll_rates": {"m0_to_m1": 0.04, "m1_to_m2": 0.55,
                               "m2_to_m3plus": 0.62},
            },
            "l5": {
                "has_compliance_issue": not compliant,
                "di_ratios": [
                    {"group": "young_vs_core", "group_zh": "年轻客群",
                     "group_en": "Young vs Core",
                     "di_ratio": 0.92 if compliant else 0.77,
                     "compliant": compliant},
                ],
            },
        }

    strategy_ids = ["v2.2", "v2.3"] + (["v2.4-Beta"] if beta else [])
    layers = {"_summary": [_summary_row(s) for s in strategy_ids]}
    for sid in strategy_ids:
        layers[sid] = _strategy_layers(
            compliant=beta_compliant if sid == "v2.4-Beta" else True)
    layers["_swap_chall_vs_champ"] = {
        "double_approve": {"n": 200, "pct": 0.2, "bad_rate": 0.015},
        "swap_in": {"n": 100, "pct": 0.1, "bad_rate": 0.03},
        "swap_out": {"n": 50, "pct": 0.05, "bad_rate": 0.06},
        "double_reject": {"n": 650, "pct": 0.65},
        "consistency_pct": 0.85,
    }
    return {
        "run_id": "r-test", "sample_size": 1000, "duration_s": 1.23,
        "snapshot_sha": "abc123def456",
        "champion": "v2.2", "challenger": "v2.3",
        "beta": "v2.4-Beta" if beta else None,
        "layers": layers,
    }


class TestStaticReportZh:
    def test_contains_all_sections(self):
        md = _build_static_report(_raw_run(), language="zh")
        for section in ("回测报告", "策略配置", "L1-L2 核心 KPI",
                        "L3 风险指标", "L4 换组分析", "L5 公平性合规", "结论与建议"):
            assert section in md, section

    def test_kpis_formatted_as_percentages(self):
        md = _build_static_report(_raw_run(), language="zh")
        assert "28.0%" in md   # approval_rate 0.28
        assert "1.8%" in md    # bad_rate 0.018
        assert "0.7800" in md  # auc quoted as-is

    def test_swap_quadrants_rendered(self):
        md = _build_static_report(_raw_run(), language="zh")
        assert "Swap-in" in md and "决策一致率" in md
        assert "85.0%" in md

    def test_noncompliant_beta_gets_remediation_line(self):
        md = _build_static_report(_raw_run(beta_compliant=False), language="zh")
        assert "整改" in md
        assert "⚠️" in md

    def test_compliant_beta_has_no_remediation_line(self):
        md = _build_static_report(_raw_run(beta_compliant=True), language="zh")
        assert "整改" not in md

    def test_run_without_beta(self):
        md = _build_static_report(_raw_run(beta=False), language="zh")
        assert "v2.4-Beta" not in md
        assert "| Beta |" not in md


class TestStaticReportEn:
    def test_contains_all_sections(self):
        md = _build_static_report(_raw_run(), language="en")
        # the EN report is a condensed variant: no L3/L4 sections
        for section in ("BackTest Studio Report", "L1-L2 Core KPI Comparison",
                        "L5 Fairness & Compliance", "Conclusion"):
            assert section in md, section

    def test_compliance_markers(self):
        good = _build_static_report(_raw_run(beta_compliant=True), language="en")
        assert "✓ Compliant" in good
        bad = _build_static_report(_raw_run(beta_compliant=False), language="en")
        assert "⚠️ Compliance Issue" in bad
        assert "remediation" in bad

    def test_missing_summary_yields_na(self):
        run = _raw_run()
        run["layers"]["_summary"] = []
        md = _build_static_report(run, language="en")
        assert "N/A" in md


# ---------------------------------------------------------------------------
# Lifespan (startup/shutdown handlers in main.py)
# ---------------------------------------------------------------------------

class TestLifespan:
    def test_startup_initialises_db_and_serves(self):
        with TestClient(app) as client:  # context manager runs the lifespan
            resp = client.get("/api/health")
            assert resp.status_code == 200
            # rehydration ran: history endpoint is queryable right after boot
            assert client.get("/api/experiments/history").status_code == 200


# ---------------------------------------------------------------------------
# Stability service
# ---------------------------------------------------------------------------

class TestStability:
    def test_psi_trend_has_n_months_with_status(self):
        trend = stability.compute_psi_trend("v2.3", n_months=3)
        assert len(trend) == 3
        for pt in trend:
            assert pt["psi"] >= 0
            assert pt["status"] in ("stable", "moderate_shift", "major_shift")
            assert pt["n_reference"] > 0 and pt["n_current"] > 0

    def test_psi_trend_is_deterministic(self):
        a = stability.compute_psi_trend("v2.2", n_months=2)
        b = stability.compute_psi_trend("v2.2", n_months=2)
        assert a == b

    def test_csi_defaults_to_score_and_dti(self):
        out = stability.compute_csi("v2.3")
        assert {r["feature"] for r in out} == {"score", "dti"}
        for r in out:
            assert r["stable"] == (r["csi"] < 0.10)

    def test_csi_skips_unknown_features(self):
        out = stability.compute_csi("v2.3", features=["score", "not_a_column"])
        assert {r["feature"] for r in out} == {"score"}

    def test_score_distribution_default_dataset(self):
        out = stability.compute_score_distribution("v2.2", bins=10)
        assert len(out["approved_distribution"]) == 10
        assert len(out["rejected_distribution"]) == 10
        # rejected population sits lower on the score axis than approved
        assert out["rejected_mean"] < out["approved_mean"]
        for bucket in out["approved_distribution"]:
            assert bucket["score_low"] < bucket["score_high"]
