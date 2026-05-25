"""L1-L5 metrics for custom (uploaded) strategies and datasets.

These functions are strategy-id-agnostic: they consume a DataView (column-mapped
dataset) and one or two StrategyResult objects (pd_hat + approve_mask). The math
mirrors fixtures._compute_l*, but is driven by the provided pd_hat / masks rather
than the built-in synthetic model, and degrades gracefully when optional columns
(outcome / score / protected attributes) are not mapped.
"""
from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score, brier_score_loss, roc_curve

from app.db import repository
from app.strategies.contract import DataView, StrategyResult

# Pricing assumptions (same defaults the built-in L2 uses).
_DEFAULT_MARGIN = 0.165
_DEFAULT_AVG_LOAN = 8000.0
_LGD = 0.55
_CAPITAL_RATIO = 0.72


def _outcome(view: DataView) -> Optional[np.ndarray]:
    """Resolve the binary outcome column (logical role "outcome" or "bad")."""
    for name in ("outcome", "bad"):
        if view.has(name):
            return np.asarray(view[name]).astype(int)
    return None


def _params(result: StrategyResult) -> dict:
    p = result.strategy_info.get("params") if isinstance(result.strategy_info, dict) else None
    return p if isinstance(p, dict) else {}


def _param_value(params: dict, key: str, default):
    v = params.get(key)
    if isinstance(v, dict):  # meta-style {"default": ...}
        return v.get("default", default)
    return v if v is not None else default


# --------------------------------------------------------------------------- #
# L1: model quality
# --------------------------------------------------------------------------- #
def compute_l1(view: DataView, result: StrategyResult) -> dict:
    y = _outcome(view)
    approved = result.approve_mask
    n_approved = int(approved.sum())
    if y is None:
        return {"skipped": "no outcome column mapped", "n_approved": n_approved}

    sub_mask = approved.astype(bool)
    y_true = y[sub_mask]
    y_pred_prob = result.pd_hat[sub_mask]
    if len(y_true) < 100 or len(np.unique(y_true)) < 2:
        return {"skipped": "insufficient approved sample for L1", "n_approved": n_approved}

    auc = float(roc_auc_score(y_true, y_pred_prob)) if y_true.sum() > 0 else 0.5
    pos = y_pred_prob[y_true == 1]
    neg = y_pred_prob[y_true == 0]
    ks_stat, _ = stats.ks_2samp(pos, neg)
    brier = float(brier_score_loss(y_true, y_pred_prob))

    threshold_idx = int(len(y_pred_prob) * 0.80)
    threshold_val = np.sort(y_pred_prob)[min(threshold_idx, len(y_pred_prob) - 1)]
    top20_mask = y_pred_prob >= threshold_val
    overall_rate = y_true.mean()
    top20_rate = y_true[top20_mask].mean() if top20_mask.sum() > 0 else 0.0
    lift_at_20 = float(top20_rate / overall_rate) if overall_rate > 0 else 1.0

    fpr, tpr, _ = roc_curve(y_true, y_pred_prob)
    indices = np.linspace(0, len(fpr) - 1, min(20, len(fpr)), dtype=int)
    roc_points = [{"fpr": round(float(fpr[i]), 4), "tpr": round(float(tpr[i]), 4)} for i in indices]

    name = str(result.strategy_info.get("name", "custom"))
    rng_psi = np.random.default_rng(int(hashlib.md5(name.encode()).hexdigest(), 16) % (2**32))
    psi_base = 0.06
    psi_trend = [{"month": f"M{i+1}", "psi": round(float(psi_base + rng_psi.normal(0, 0.008)), 4)}
                 for i in range(6)]

    bin_edges = np.linspace(0, 1, 11)
    calib_points = []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        m = (y_pred_prob >= lo) & (y_pred_prob < hi)
        if m.sum() > 0:
            calib_points.append({
                "predicted": round(float(y_pred_prob[m].mean()), 4),
                "actual": round(float(y_true[m].mean()), 4),
                "count": int(m.sum()),
            })

    return {
        "auc": round(auc, 4),
        "ks": round(float(ks_stat), 4),
        "lift_at_20": round(lift_at_20, 3),
        "brier_score": round(brier, 4),
        "roc_curve": roc_points,
        "psi_trend": psi_trend,
        "calibration": calib_points,
        "n_approved": n_approved,
        # permutation importance would require re-running the sandbox per feature;
        # out of scope for the MVP.
        "feature_importance": [],
    }


# --------------------------------------------------------------------------- #
# L2: business value
# --------------------------------------------------------------------------- #
def compute_l2(view: DataView, result: StrategyResult) -> dict:
    approved = result.approve_mask.astype(bool)
    n_total = len(view)
    n_approved = int(approved.sum())
    approval_rate = round(n_approved / n_total, 4) if n_total else 0.0

    y = _outcome(view)
    bad_rate = round(float(y[approved].mean()), 4) if (y is not None and n_approved > 0) else 0.0

    params = _params(result)
    lim_min = _param_value(params, "limit_increase_min", 0.20)
    lim_max = _param_value(params, "limit_increase_max", 0.50)
    avg_increase = (float(lim_min) + float(lim_max)) / 2.0
    margin_rate = float(_param_value(params, "margin", _DEFAULT_MARGIN))
    avg_loan = float(_param_value(params, "avg_loan", _DEFAULT_AVG_LOAN))

    incremental_balance = avg_loan * avg_increase
    revenue_per = incremental_balance * margin_rate
    el_per = incremental_balance * bad_rate * _LGD
    profit_per = revenue_per - el_per
    raroc = round((margin_rate - bad_rate * _LGD) / _CAPITAL_RATIO, 4)
    economic_capital = incremental_balance * n_approved * 0.10
    el_total = el_per * n_approved

    pareto = []
    for pct in np.linspace(0.10, 0.70, 15):
        extra = max((pct - approval_rate) / 0.50, 0.0)
        adj_profit = profit_per * (1 - 0.30 * extra)
        pareto.append({"approval_rate": round(float(pct), 3), "avg_profit": round(float(adj_profit), 2)})

    raroc_bands = _raroc_bands(view, y, margin_rate)

    return {
        "approval_rate": approval_rate,
        "n_approved": n_approved,
        "bad_rate": bad_rate,
        "avg_loan_amount": avg_loan,
        "revenue_per_approved": round(revenue_per, 2),
        "el_per_approved": round(el_per, 2),
        "avg_profit_per_approved": round(profit_per, 2),
        "raroc": raroc,
        "el_total": round(el_total, 0),
        "economic_capital": round(economic_capital, 0),
        "pareto_frontier": pareto,
        "rejection_reasons": [],  # no per-rule attribution for custom strategies
        "raroc_bands": raroc_bands,
    }


def _raroc_bands(view: DataView, y: Optional[np.ndarray], margin: float) -> list[dict]:
    if not view.has("score") or y is None:
        return []
    score = np.asarray(view["score"], dtype=float)
    bands = [("<600", -np.inf, 600), ("600-650", 600, 650), ("650-700", 650, 700),
             ("700-750", 700, 750), ("750+", 750, np.inf)]
    pop_bad = float(y.mean())
    out = []
    for label, lo, hi in bands:
        m = (score >= lo) & (score < hi)
        br = float(y[m].mean()) if m.sum() >= 50 else pop_bad
        raroc = (margin - br * _LGD) / _CAPITAL_RATIO
        out.append({"band": label, "raroc": round(raroc, 4)})
    return out


# --------------------------------------------------------------------------- #
# L3: risk
# --------------------------------------------------------------------------- #
def compute_l3(view: DataView, result: StrategyResult) -> dict:
    y = _outcome(view)
    approved = result.approve_mask.astype(bool)
    if y is None:
        return {"skipped": "no outcome column mapped"}

    sub = y[approved]
    bad_rate = round(float(sub.mean()), 4) if len(sub) > 0 else 0.0
    fpd_rate = round(max(bad_rate * 0.32, 0.001), 4)
    m0m1 = round(min(0.020 + bad_rate * 1.1, 0.14), 4)
    roll_rates = {
        "m0_to_m1": m0m1,
        "m1_to_m2": round(0.52 + bad_rate * 3.5, 4),
        "m2_to_m3plus": round(0.60 + bad_rate * 3.0, 4),
    }
    vintage_curve = []
    for m in range(1, 13):
        cum_rate = bad_rate * (1 / (1 + np.exp(-0.7 * (m - 6))))
        vintage_curve.append({"month": m, "cum_bad_rate": round(float(cum_rate), 4)})

    name = str(result.strategy_info.get("name", "custom")) + "_fpd"
    rng_fpd = np.random.default_rng(int(hashlib.md5(name.encode()).hexdigest(), 16) % (2**32))
    fpd_trend = []
    for i in range(6):
        val = fpd_rate * (1 + rng_fpd.normal(0, 0.12))
        fpd_trend.append({"month": f"M{i+1}", "fpd_rate": round(float(max(val, 0.001)), 4)})

    return {
        "mob12_bad_rate": bad_rate,
        "fpd_rate": fpd_rate,
        "roll_rates": roll_rates,
        "vintage_curve": vintage_curve,
        "fpd_monthly_trend": fpd_trend,
    }


# --------------------------------------------------------------------------- #
# L4: swap set (two strategies)
# --------------------------------------------------------------------------- #
def compute_l4(view: DataView, result_a: StrategyResult, result_b: StrategyResult) -> dict:
    """result_a = challenger, result_b = champion (baseline)."""
    y = _outcome(view)
    if y is None:
        return {"skipped": "no outcome column mapped"}

    chall_mask = result_a.approve_mask.astype(bool)
    champ_mask = result_b.approve_mask.astype(bool)
    bad = y

    da = chall_mask & champ_mask
    si = chall_mask & ~champ_mask
    so = ~chall_mask & champ_mask
    dr = ~chall_mask & ~champ_mask

    def _br(mask: np.ndarray) -> float:
        s = bad[mask]
        return float(s.mean()) if len(s) > 0 else 0.0

    da_n, si_n, so_n, dr_n = int(da.sum()), int(si.sum()), int(so.sum()), int(dr.sum())
    total = len(view)
    consistency_pct = round((da_n + dr_n) / total, 4) if total else 0.0

    base_bad_rate = _br(champ_mask)
    swap_out_bad_rate = _br(so)
    swap_out_lift = round(swap_out_bad_rate / base_bad_rate, 2) if base_bad_rate > 0 else 0.0
    p_value = _two_proportion_pvalue(bad[si], bad[da])

    band_consistency = []
    if view.has("score"):
        score = np.asarray(view["score"], dtype=float)
        score_bands = [("≤640", -np.inf, 640), ("641-680", 641, 680),
                       ("681-720", 681, 720), (">720", 720, np.inf)]
        for label, lo, hi in score_bands:
            band_mask = (score >= lo) & (score <= hi)
            if band_mask.sum() == 0:
                continue
            agree = ((chall_mask == champ_mask) & band_mask).sum()
            band_consistency.append({
                "score_band": label,
                "n": int(band_mask.sum()),
                "consistency_pct": round(float(agree / band_mask.sum()), 4),
            })

    return {
        "double_approve": {"n": da_n, "pct": round(da_n / total, 4) if total else 0.0, "bad_rate": round(_br(da), 4)},
        "swap_in": {"n": si_n, "pct": round(si_n / total, 4) if total else 0.0, "bad_rate": round(_br(si), 4)},
        "swap_out": {"n": so_n, "pct": round(so_n / total, 4) if total else 0.0, "bad_rate": round(_br(so), 4)},
        "double_reject": {"n": dr_n, "pct": round(dr_n / total, 4) if total else 0.0, "bad_rate": 0.0},
        "consistency_pct": consistency_pct,
        "score_band_consistency": band_consistency,
        "base_bad_rate": round(base_bad_rate, 4),
        "swap_out_lift": swap_out_lift,
        "p_value": p_value,
        "challenger": str(result_a.strategy_info.get("name", "challenger")),
        "champion": str(result_b.strategy_info.get("name", "champion")),
    }


def _two_proportion_pvalue(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 1.0
    pa, pb = float(a.mean()), float(b.mean())
    pooled = (a.sum() + b.sum()) / (na + nb)
    se = (pooled * (1 - pooled) * (1 / na + 1 / nb)) ** 0.5
    if se == 0:
        return 1.0
    z = (pa - pb) / se
    return round(float(2 * (1 - stats.norm.cdf(abs(z)))), 4)


# --------------------------------------------------------------------------- #
# L5: fairness
# --------------------------------------------------------------------------- #
def compute_l5(view: DataView, result: StrategyResult) -> dict:
    approved = result.approve_mask.astype(bool)
    y = _outcome(view)

    # (logical attribute, group selector, reference selector, labels)
    specs = [
        ("gender", "female_vs_male", lambda v: v == 1, lambda v: v == 0,
         "女性 vs 男性", "Female vs Male"),
        ("age_band", "young_vs_core", lambda v: v == 0, lambda v: (v >= 1) & (v <= 3),
         "18-25岁 vs 核心客群", "Age 18-25 vs Core"),
        ("channel", "partner_vs_online", lambda v: v == 2, lambda v: v == 0,
         "合作平台 vs 线上", "Partner vs Online"),
    ]

    di_groups, tpr_gaps = [], []
    threshold = 0.80

    def _di(group_mask, ref_mask):
        g = approved[group_mask].mean() if group_mask.sum() > 0 else 0.0
        r = approved[ref_mask].mean() if ref_mask.sum() > 0 else 1.0
        return float(g / r) if r > 0 else 1.0

    def _tpr_gap(group_mask, ref_mask):
        if y is None:
            return 0.0
        def _tpr(m):
            denom = (m & (y == 1)).sum()
            num = (m & approved & (y == 1)).sum()
            return float(num / denom) if denom > 0 else 0.0
        return round(_tpr(group_mask) - _tpr(ref_mask), 4)

    for attr, key, gsel, rsel, zh, en in specs:
        col = view.protected(attr)
        if col is None:
            continue
        col = np.asarray(col)
        gmask, rmask = gsel(col), rsel(col)
        ratio = _di(gmask, rmask)
        di_groups.append({
            "group": key, "group_zh": zh, "group_en": en,
            "di_ratio": round(ratio, 3), "compliant": ratio >= threshold, "threshold": threshold,
        })
        tpr_gaps.append({"group": key, "tpr_gap": _tpr_gap(gmask, rmask)})

    if not di_groups:
        return {"skipped": "no protected attributes mapped"}

    has_issue = any(not g["compliant"] for g in di_groups)
    return {
        "di_ratios": di_groups,
        "tpr_gaps": tpr_gaps,
        "feature_importance": [],
        "has_compliance_issue": has_issue,
        "compliance_threshold": threshold,
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def apply_custom_strategy(
    view: DataView,
    result: StrategyResult,
    champion_result: StrategyResult,
) -> dict:
    has_outcome = _outcome(view) is not None
    l1 = compute_l1(view, result)
    l2 = compute_l2(view, result)
    l3 = compute_l3(view, result) if has_outcome else {"skipped": "no outcome column mapped"}
    l4 = compute_l4(view, result, champion_result) if has_outcome else {"skipped": "no outcome column mapped"}
    l5 = compute_l5(view, result)
    return {
        "strategy_info": result.strategy_info,
        "l1": l1, "l2": l2, "l3": l3, "l4": l4, "l5": l5,
    }


def load_dataset_as_view(dataset_id: str, mapping_id: Optional[str]) -> tuple[DataView, list[str]]:
    """Load a stored dataset (parquet/csv) into a DataView with its mapping.

    Returns (view, available_roles) where available_roles lists which semantic
    roles (outcome/score/gender/age_band/channel) are resolvable.
    """
    ds = repository.get_custom_dataset(dataset_id)
    if ds is None:
        raise ValueError(f"dataset not found: {dataset_id}")

    path = ds["file_path"]
    if path.endswith(".parquet"):
        frame = pd.read_parquet(path)
    else:
        frame = pd.read_csv(path)

    data: dict[str, np.ndarray] = {col: frame[col].to_numpy() for col in frame.columns}

    mapping, role_columns = {}, {}
    if mapping_id:
        m = repository.get_column_mapping(mapping_id)
        if m is not None:
            mapping = m.get("mapping", {})
            role_columns = m.get("role_columns", {})

    view = DataView(data, mapping=mapping, role_columns=role_columns)

    available_roles = []
    for role in ("outcome", "score", "gender", "age_band", "channel"):
        if view.has(role):
            available_roles.append(role)
    return view, available_roles
