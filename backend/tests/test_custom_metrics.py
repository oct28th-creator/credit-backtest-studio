"""Tests for DataView and the custom-strategy L1-L5 metric functions.

Focus: the metrics must produce sane numbers when all columns are mapped, and
must degrade gracefully (skip, not crash) when optional columns — outcome,
score, protected attributes — are absent.
"""
import numpy as np
import pytest

from app.services import custom_metrics
from app.strategies.builtin_adapter import build_builtin_result
from app.strategies.contract import DataView, StrategyResult
from app.data.fixtures import generate_synthetic_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_data(n=2000, seed=7):
    rng = np.random.default_rng(seed)
    score = rng.uniform(560.0, 820.0, n)
    bad_prob = np.clip(1.3 - score / 650.0, 0.02, 0.85)
    bad = (rng.uniform(0, 1, n) < bad_prob).astype(int)
    sex = rng.integers(0, 2, n)
    return {"credit_score": score, "is_bad": bad, "sex": sex}


def make_view(n=2000, with_outcome=True, with_score=True, with_protected=True):
    data = make_data(n)
    roles = {}
    if with_outcome:
        roles["outcome"] = "is_bad"
    else:
        del data["is_bad"]
    if with_score:
        roles["score"] = "credit_score"
    if with_protected:
        roles["gender"] = "sex"
    else:
        del data["sex"]
    return DataView(data, mapping={"score": "credit_score"}, role_columns=roles)


def make_result(view, cutoff=0.5, name="chall"):
    score = np.asarray(view["score"], dtype=float)
    pd_hat = np.clip((850.0 - score) / 350.0, 0.0, 1.0)
    return StrategyResult(
        approve_mask=pd_hat < cutoff,
        pd_hat=pd_hat,
        strategy_info={"name": name, "params": {}},
    )


@pytest.fixture(scope="module")
def view():
    return make_view()


@pytest.fixture(scope="module")
def challenger(view):
    return make_result(view, cutoff=0.60, name="chall")


@pytest.fixture(scope="module")
def champion(view):
    return make_result(view, cutoff=0.50, name="champ")


# ---------------------------------------------------------------------------
# DataView
# ---------------------------------------------------------------------------

class TestDataView:
    def test_mapping_resolves_logical_names(self, view):
        assert view.has("score")
        np.testing.assert_array_equal(view["score"], view["credit_score"])

    def test_role_columns_resolve(self, view):
        np.testing.assert_array_equal(view["outcome"], view["is_bad"])

    def test_missing_column_raises_keyerror(self, view):
        with pytest.raises(KeyError):
            view["nonexistent"]

    def test_protected_returns_none_when_absent(self, view):
        assert view.protected("channel") is None
        assert view.protected("gender") is not None

    def test_as_feature_dict_skips_missing(self, view):
        out = view.as_feature_dict(["score", "not_there"])
        assert set(out.keys()) == {"score"}

    def test_len(self, view):
        assert len(view) == 2000

    def test_structured_array_source(self):
        arr = np.zeros(10, dtype=[("a", "f8"), ("b", "i4")])
        v = DataView(arr, mapping={"x": "a"})
        assert len(v) == 10
        assert v.has("x") and v.has("b")
        assert not v.has("c")


# ---------------------------------------------------------------------------
# L1 model quality
# ---------------------------------------------------------------------------

class TestL1:
    def test_full_metrics_with_outcome(self, view, challenger):
        l1 = custom_metrics.compute_l1(view, challenger)
        assert "skipped" not in l1
        assert 0.5 < l1["auc"] <= 1.0
        assert 0.0 < l1["ks"] <= 1.0
        assert 0.0 <= l1["brier_score"] <= 1.0
        assert len(l1["psi_trend"]) == 6
        assert l1["n_approved"] == int(challenger.approve_mask.sum())
        assert len(l1["roc_curve"]) > 0

    def test_skipped_without_outcome(self, challenger):
        no_outcome = make_view(with_outcome=False)
        result = make_result(no_outcome, cutoff=0.60)
        l1 = custom_metrics.compute_l1(no_outcome, result)
        assert "no outcome" in l1["skipped"]

    def test_skipped_with_insufficient_approved_sample(self, view):
        small = StrategyResult(
            approve_mask=np.arange(len(view)) < 50,  # only 50 approved
            pd_hat=np.full(len(view), 0.1),
            strategy_info={"name": "tiny"},
        )
        l1 = custom_metrics.compute_l1(view, small)
        assert "insufficient" in l1["skipped"]

    def test_deterministic_psi_per_strategy_name(self, view, challenger):
        a = custom_metrics.compute_l1(view, challenger)
        b = custom_metrics.compute_l1(view, challenger)
        assert a["psi_trend"] == b["psi_trend"]


# ---------------------------------------------------------------------------
# L2 business value
# ---------------------------------------------------------------------------

class TestL2:
    def test_approval_rate_matches_mask(self, view, challenger):
        l2 = custom_metrics.compute_l2(view, challenger)
        expected = round(challenger.approve_mask.sum() / len(view), 4)
        assert l2["approval_rate"] == expected
        assert l2["n_approved"] == int(challenger.approve_mask.sum())

    def test_raroc_formula(self, view, challenger):
        l2 = custom_metrics.compute_l2(view, challenger)
        margin, lgd, cap = 0.165, 0.55, 0.72
        expected = round((margin - l2["bad_rate"] * lgd) / cap, 4)
        assert l2["raroc"] == expected

    def test_works_without_outcome(self):
        no_outcome = make_view(with_outcome=False)
        result = make_result(no_outcome, cutoff=0.60)
        l2 = custom_metrics.compute_l2(no_outcome, result)
        assert l2["bad_rate"] == 0.0
        assert l2["approval_rate"] > 0

    def test_raroc_bands_present_with_score_and_outcome(self, view, challenger):
        l2 = custom_metrics.compute_l2(view, challenger)
        assert len(l2["raroc_bands"]) == 5
        assert {b["band"] for b in l2["raroc_bands"]} == {
            "<600", "600-650", "650-700", "700-750", "750+"}

    def test_raroc_bands_empty_without_outcome(self):
        no_outcome = make_view(with_outcome=False)
        result = make_result(no_outcome)
        l2 = custom_metrics.compute_l2(no_outcome, result)
        assert l2["raroc_bands"] == []

    def test_pareto_frontier_shape(self, view, challenger):
        l2 = custom_metrics.compute_l2(view, challenger)
        assert len(l2["pareto_frontier"]) == 15
        for pt in l2["pareto_frontier"]:
            assert 0.0 < pt["approval_rate"] <= 0.7


# ---------------------------------------------------------------------------
# L3 risk
# ---------------------------------------------------------------------------

class TestL3:
    def test_full_metrics_with_outcome(self, view, challenger):
        l3 = custom_metrics.compute_l3(view, challenger)
        assert "skipped" not in l3
        assert 0.0 <= l3["mob12_bad_rate"] <= 1.0
        assert l3["fpd_rate"] > 0
        assert set(l3["roll_rates"].keys()) == {"m0_to_m1", "m1_to_m2", "m2_to_m3plus"}

    def test_vintage_curve_12_months_monotone(self, view, challenger):
        l3 = custom_metrics.compute_l3(view, challenger)
        curve = l3["vintage_curve"]
        assert len(curve) == 12
        rates = [pt["cum_bad_rate"] for pt in curve]
        assert rates == sorted(rates)

    def test_skipped_without_outcome(self):
        no_outcome = make_view(with_outcome=False)
        result = make_result(no_outcome)
        l3 = custom_metrics.compute_l3(no_outcome, result)
        assert "no outcome" in l3["skipped"]


# ---------------------------------------------------------------------------
# L4 swap set
# ---------------------------------------------------------------------------

class TestL4:
    def test_quadrants_partition_population(self, view, challenger, champion):
        l4 = custom_metrics.compute_l4(view, challenger, champion)
        total = sum(l4[q]["n"] for q in
                    ("double_approve", "swap_in", "swap_out", "double_reject"))
        assert total == len(view)
        pct_sum = sum(l4[q]["pct"] for q in
                      ("double_approve", "swap_in", "swap_out", "double_reject"))
        assert pct_sum == pytest.approx(1.0, abs=0.001)

    def test_consistency_and_pvalue_in_range(self, view, challenger, champion):
        l4 = custom_metrics.compute_l4(view, challenger, champion)
        assert 0.0 <= l4["consistency_pct"] <= 1.0
        assert 0.0 <= l4["p_value"] <= 1.0

    def test_swap_in_present_when_challenger_looser(self, view, challenger, champion):
        # challenger cutoff 0.60 approves a superset of champion cutoff 0.50
        l4 = custom_metrics.compute_l4(view, challenger, champion)
        assert l4["swap_in"]["n"] > 0
        assert l4["swap_out"]["n"] == 0

    def test_score_band_consistency_present_with_score(self, view, challenger, champion):
        l4 = custom_metrics.compute_l4(view, challenger, champion)
        assert len(l4["score_band_consistency"]) > 0
        for band in l4["score_band_consistency"]:
            assert 0.0 <= band["consistency_pct"] <= 1.0

    def test_skipped_without_outcome(self):
        no_outcome = make_view(with_outcome=False)
        a = make_result(no_outcome, cutoff=0.60)
        b = make_result(no_outcome, cutoff=0.50)
        l4 = custom_metrics.compute_l4(no_outcome, a, b)
        assert "no outcome" in l4["skipped"]


# ---------------------------------------------------------------------------
# L5 fairness
# ---------------------------------------------------------------------------

class TestL5:
    def test_di_ratio_present_for_mapped_gender(self, view, challenger):
        l5 = custom_metrics.compute_l5(view, challenger)
        assert "skipped" not in l5
        groups = {g["group"] for g in l5["di_ratios"]}
        assert groups == {"female_vs_male"}  # only gender is mapped
        for g in l5["di_ratios"]:
            assert g["di_ratio"] > 0
            assert g["compliant"] == (g["di_ratio"] >= 0.80)

    def test_tpr_gaps_align_with_di_groups(self, view, challenger):
        l5 = custom_metrics.compute_l5(view, challenger)
        assert len(l5["tpr_gaps"]) == len(l5["di_ratios"])

    def test_skipped_without_protected_attributes(self):
        bare = make_view(with_protected=False)
        result = make_result(bare)
        l5 = custom_metrics.compute_l5(bare, result)
        assert "no protected attributes" in l5["skipped"]


# ---------------------------------------------------------------------------
# Orchestration + builtin adapter
# ---------------------------------------------------------------------------

class TestApplyCustomStrategy:
    def test_all_layers_present_with_full_mapping(self, view, challenger, champion):
        out = custom_metrics.apply_custom_strategy(view, challenger, champion)
        for layer in ("l1", "l2", "l3", "l4", "l5"):
            assert "skipped" not in out[layer], layer
        assert out["strategy_info"]["name"] == "chall"

    def test_degrades_without_outcome(self):
        no_outcome = make_view(with_outcome=False)
        a = make_result(no_outcome, cutoff=0.60)
        b = make_result(no_outcome, cutoff=0.50)
        out = custom_metrics.apply_custom_strategy(no_outcome, a, b)
        assert "skipped" in out["l1"]
        assert "skipped" in out["l3"]
        assert "skipped" in out["l4"]
        assert "skipped" not in out["l2"]  # L2 always computes
        assert "skipped" not in out["l5"]  # gender still mapped

    def test_degrades_without_protected(self):
        bare = make_view(with_protected=False)
        a = make_result(bare, cutoff=0.60)
        b = make_result(bare, cutoff=0.50)
        out = custom_metrics.apply_custom_strategy(bare, a, b)
        assert "skipped" in out["l5"]
        assert "skipped" not in out["l1"]


@pytest.fixture(scope="module")
def df():
    return generate_synthetic_data(n=10000, seed=42)


class TestBuiltinAdapter:
    def test_wraps_builtin_strategy(self, df):
        res = build_builtin_result(df, "v2.2")
        assert len(res.approve_mask) == len(df)
        assert res.pd_hat.min() >= 0.0 and res.pd_hat.max() <= 1.0
        assert res.strategy_info["id"] == "v2.2"
        assert 0 < res.approve_mask.sum() < len(df)

    def test_unknown_strategy_raises(self, df):
        with pytest.raises(ValueError, match="Unknown strategy"):
            build_builtin_result(df, "v9.9")
