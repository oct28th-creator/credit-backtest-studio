"""
Fairness metrics: Disparate Impact Ratio and TPR gap for protected groups.
"""
from __future__ import annotations

import numpy as np
from typing import Optional

from app.data.fixtures import generate_synthetic_data, _approve_mask, STRATEGIES


def compute_fairness_report(
    strategy_id: str,
    df: Optional[np.ndarray] = None,
    seed: int = 42,
) -> dict:
    """
    Compute DI Ratio and TPR gap for all protected groups under a strategy.

    Groups evaluated:
      - gender: female (1) vs male (0)
      - age: young 18-25 (band=0) vs core 26-55 (band 1-3)
      - channel: partner (2) vs online (0)
    """
    if df is None:
        df = generate_synthetic_data(seed=seed)

    if strategy_id not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_id}")

    approved = _approve_mask(df, strategy_id)
    bad = df["bad"].astype(int)

    groups = {
        "female_vs_male": {
            "group_mask": df["gender"] == 1,
            "ref_mask": df["gender"] == 0,
            "label_zh": "女性 vs 男性",
            "label_en": "Female vs Male",
        },
        "young_vs_core": {
            "group_mask": df["age_band"] == 0,
            "ref_mask": (df["age_band"] >= 1) & (df["age_band"] <= 3),
            "label_zh": "18-25岁 vs 核心客群",
            "label_en": "Age 18-25 vs Core (26-55)",
        },
        "partner_vs_online": {
            "group_mask": df["channel"] == 2,
            "ref_mask": df["channel"] == 0,
            "label_zh": "合作平台 vs 线上渠道",
            "label_en": "Partner Channel vs Online",
        },
    }

    results = []
    for key, g in groups.items():
        gm = g["group_mask"]
        rm = g["ref_mask"]

        # Approval rates
        group_apr = float(approved[gm].mean()) if gm.sum() > 0 else 0.0
        ref_apr = float(approved[rm].mean()) if rm.sum() > 0 else 1.0
        di_ratio = group_apr / ref_apr if ref_apr > 0 else 1.0

        # True Positive Rate (approved given bad=1)
        def _tpr(mask: np.ndarray) -> float:
            bads = bad[mask]
            appr_bads = bad[mask & approved.astype(bool)]
            total_bad = int((bads == 1).sum())
            appr_bad = int((appr_bads == 1).sum())
            return appr_bad / total_bad if total_bad > 0 else 0.0

        tpr_group = _tpr(gm)
        tpr_ref = _tpr(rm)
        tpr_gap = round(tpr_group - tpr_ref, 4)

        # Bad rate within approved subgroup
        group_approved = gm & approved.astype(bool)
        ref_approved = rm & approved.astype(bool)
        group_bad_rate = float(bad[group_approved].mean()) if group_approved.sum() > 0 else 0.0
        ref_bad_rate = float(bad[ref_approved].mean()) if ref_approved.sum() > 0 else 0.0

        results.append({
            "group": key,
            "group_zh": g["label_zh"],
            "group_en": g["label_en"],
            "group_approval_rate": round(group_apr, 4),
            "ref_approval_rate": round(ref_apr, 4),
            "di_ratio": round(di_ratio, 3),
            "compliant": di_ratio >= 0.80,
            "threshold": 0.80,
            "tpr_gap": tpr_gap,
            "group_bad_rate": round(group_bad_rate, 4),
            "ref_bad_rate": round(ref_bad_rate, 4),
            "group_n": int(gm.sum()),
            "ref_n": int(rm.sum()),
        })

    has_issue = any(not r["compliant"] for r in results)

    return {
        "strategy_id": strategy_id,
        "fairness_groups": results,
        "has_compliance_issue": has_issue,
        "compliance_threshold": 0.80,
        "note_zh": "DI Ratio < 0.80 为合规红线，需立即整改",
        "note_en": "DI Ratio below 0.80 triggers compliance review",
    }


def compute_shap_feature_importance(strategy_id: str) -> list[dict]:
    """Return simulated SHAP-style feature importance for a strategy."""
    shap_map = {
        "v2.2": [
            {"feature": "月负债率", "feature_en": "Monthly Debt Ratio", "importance": 0.22, "direction": "negative"},
            {"feature": "多头借贷数", "feature_en": "Multi-loan Count", "importance": 0.25, "direction": "negative"},
            {"feature": "信用查询数", "feature_en": "Credit Inquiries", "importance": 0.21, "direction": "negative"},
            {"feature": "工作年限", "feature_en": "Employment Years", "importance": 0.17, "direction": "positive"},
            {"feature": "年龄", "feature_en": "Age", "importance": 0.15, "direction": "positive"},
        ],
        "v2.3": [
            {"feature": "月负债率", "feature_en": "Monthly Debt Ratio", "importance": 0.35, "direction": "negative"},
            {"feature": "多头借贷数", "feature_en": "Multi-loan Count", "importance": 0.22, "direction": "negative"},
            {"feature": "信用查询数", "feature_en": "Credit Inquiries", "importance": 0.18, "direction": "negative"},
            {"feature": "工作年限", "feature_en": "Employment Years", "importance": 0.14, "direction": "positive"},
            {"feature": "年龄", "feature_en": "Age", "importance": 0.11, "direction": "positive"},
        ],
        "v2.4-Beta": [
            {"feature": "行为数据", "feature_en": "Behavioral Data", "importance": 0.30, "direction": "positive"},
            {"feature": "月负债率", "feature_en": "Monthly Debt Ratio", "importance": 0.28, "direction": "negative"},
            {"feature": "消费模式", "feature_en": "Spending Pattern", "importance": 0.20, "direction": "positive"},
            {"feature": "还款习惯", "feature_en": "Repayment Habit", "importance": 0.15, "direction": "positive"},
            {"feature": "年龄", "feature_en": "Age", "importance": 0.07, "direction": "positive"},
        ],
        "v2.5-RC": [
            {"feature": "月负债率", "feature_en": "Monthly Debt Ratio", "importance": 0.30, "direction": "negative"},
            {"feature": "多头借贷数", "feature_en": "Multi-loan Count", "importance": 0.23, "direction": "negative"},
            {"feature": "信用局v2特征", "feature_en": "Bureau v2 Features", "importance": 0.20, "direction": "positive"},
            {"feature": "工作年限", "feature_en": "Employment Years", "importance": 0.15, "direction": "positive"},
            {"feature": "年龄", "feature_en": "Age", "importance": 0.12, "direction": "positive"},
        ],
    }
    return shap_map.get(strategy_id, shap_map["v2.3"])
