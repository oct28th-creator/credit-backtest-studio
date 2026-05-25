from __future__ import annotations

import hashlib
import numpy as np
from scipy import stats
from sklearn.metrics import roc_auc_score, brier_score_loss, roc_curve

# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------

STRATEGIES = {
    "v2.2": {
        "id": "v2.2",
        "nickname": "黑五大促 Overlimit 策略",
        "name": "Champion v2.2",
        "role": "champion",
        "online_since": "2023-04",
        "desc_zh": "当前线上基线策略，稳定运行 18 个月。评分门槛保守（≥680），严格 DTI 控制（≤0.60），零逾期要求（MOB12），额度提升区间 +20%~+50%。",
        "desc_en": "Current production baseline, stable for 18 months. Conservative score threshold (≥680), strict DTI (≤0.60), zero delinquency (MOB12), limit increase +20%~+50%.",
        "score_cutoff": 680,
        "dti_limit": 0.60,
        "mob_months": 12,
        "mob_dpd_max": 0,
        "limit_increase_min": 0.20,
        "limit_increase_max": 0.50,
        "anti_fraud": "standard",
        "rules": {
            "anti_fraud_rules": [
                {"rule": "velocity_check", "desc_zh": "7日申请次数 ≤ 2", "desc_en": "≤2 applications in 7 days"},
                {"rule": "device_bind", "desc_zh": "设备绑定验证", "desc_en": "Device binding verification"},
                {"rule": "id_verify", "desc_zh": "实名认证 100%", "desc_en": "100% real-name verification"},
            ],
            "if_else": [
                {"condition": "score < 680", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "dti > 0.60", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "mob12_dpd > 0", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "score >= 720", "action_zh": "提额 50%", "action_en": "Increase 50%"},
                {"condition": "score >= 680", "action_zh": "提额 20%~40%", "action_en": "Increase 20%~40%"},
            ],
            "scorecard_features": [
                {"feature": "月负债率", "weight": 22, "direction": "negative"},
                {"feature": "多头借贷数", "weight": 25, "direction": "negative"},
                {"feature": "信用查询数", "weight": 21, "direction": "negative"},
                {"feature": "工作年限", "weight": 17, "direction": "positive"},
                {"feature": "年龄", "weight": 15, "direction": "positive"},
            ],
            "decision_table": [
                {"dti_band": "≤0.40", "score_band": "≥720", "action_zh": "提额50%", "action_en": "+50%", "rate": "11.5%"},
                {"dti_band": "≤0.40", "score_band": "680-719", "action_zh": "提额30%", "action_en": "+30%", "rate": "13.0%"},
                {"dti_band": "0.40-0.60", "score_band": "≥720", "action_zh": "提额30%", "action_en": "+30%", "rate": "12.5%"},
                {"dti_band": "0.40-0.60", "score_band": "680-719", "action_zh": "提额20%", "action_en": "+20%", "rate": "14.0%"},
                {"dti_band": ">0.60", "score_band": "any", "action_zh": "拒绝", "action_en": "Reject", "rate": "—"},
            ],
            "bifurcation": [
                {"branch_zh": "高分低负债 (score≥720, dti≤0.40)", "branch_en": "High-score Low-DTI", "pct": 28, "bad_rate": 1.2},
                {"branch_zh": "中分中负债 (680-720, dti≤0.60)", "branch_en": "Mid-score Mid-DTI", "pct": 45, "bad_rate": 2.1},
                {"branch_zh": "拒绝客群 (score<680 or dti>0.60)", "branch_en": "Rejected", "pct": 27, "bad_rate": None},
            ],
        },
    },
    "v2.3": {
        "id": "v2.3",
        "nickname": "黑五大促 Overlimit 策略",
        "name": "Challenger v2.3",
        "role": "challenger",
        "desc_zh": "重训模型+联合反欺诈。评分门槛适度放开（≥650），DTI 上限提升至 0.68，MOB6 零逾期，额度提升最高 +80%。RAROC 最优策略。",
        "desc_en": "Retrained model + consortium anti-fraud. Score threshold eased (≥650), DTI up to 0.68, MOB6 zero delinquency, limit increase up to +80%. Best RAROC strategy.",
        "score_cutoff": 650,
        "dti_limit": 0.68,
        "mob_months": 6,
        "mob_dpd_max": 0,
        "limit_increase_min": 0.25,
        "limit_increase_max": 0.80,
        "anti_fraud": "consortium",
        "rules": {
            "anti_fraud_rules": [
                {"rule": "consortium_lookup", "desc_zh": "联合征信黑名单核查", "desc_en": "Consortium blacklist check"},
                {"rule": "device_fingerprint", "desc_zh": "设备指纹识别", "desc_en": "Device fingerprint"},
                {"rule": "velocity_check", "desc_zh": "30日申请次数 ≤ 3", "desc_en": "≤3 applications in 30 days"},
                {"rule": "behavior_score", "desc_zh": "行为评分 ≥ 60", "desc_en": "Behavior score ≥ 60"},
            ],
            "if_else": [
                {"condition": "score < 650", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "dti > 0.68", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "mob6_dpd > 0 (last 3m)", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "score >= 720", "action_zh": "提额 80%", "action_en": "Increase 80%"},
                {"condition": "score >= 680", "action_zh": "提额 50%~60%", "action_en": "Increase 50%~60%"},
                {"condition": "score >= 650", "action_zh": "提额 25%~40%", "action_en": "Increase 25%~40%"},
            ],
            "scorecard_features": [
                {"feature": "月负债率", "weight": 35, "direction": "negative"},
                {"feature": "多头借贷数", "weight": 22, "direction": "negative"},
                {"feature": "信用查询数", "weight": 18, "direction": "negative"},
                {"feature": "工作年限", "weight": 14, "direction": "positive"},
                {"feature": "年龄", "weight": 11, "direction": "positive"},
            ],
            "decision_table": [
                {"dti_band": "≤0.40", "score_band": "≥720", "action_zh": "提额80%", "action_en": "+80%", "rate": "10.5%"},
                {"dti_band": "≤0.40", "score_band": "680-719", "action_zh": "提额60%", "action_en": "+60%", "rate": "12.0%"},
                {"dti_band": "≤0.40", "score_band": "650-679", "action_zh": "提额40%", "action_en": "+40%", "rate": "13.5%"},
                {"dti_band": "0.40-0.68", "score_band": "≥720", "action_zh": "提额50%", "action_en": "+50%", "rate": "11.5%"},
                {"dti_band": "0.40-0.68", "score_band": "680-719", "action_zh": "提额35%", "action_en": "+35%", "rate": "13.0%"},
                {"dti_band": "0.40-0.68", "score_band": "650-679", "action_zh": "提额25%", "action_en": "+25%", "rate": "14.5%"},
                {"dti_band": ">0.68", "score_band": "any", "action_zh": "拒绝", "action_en": "Reject", "rate": "—"},
            ],
            "bifurcation": [
                {"branch_zh": "优质扩张 (score≥720, dti≤0.40)", "branch_en": "Quality Expansion", "pct": 32, "bad_rate": 1.4},
                {"branch_zh": "稳健扩张 (680-720, dti≤0.68)", "branch_en": "Stable Expansion", "pct": 42, "bad_rate": 2.8},
                {"branch_zh": "边际扩张 (650-680, dti≤0.68)", "branch_en": "Marginal Expansion", "pct": 14, "bad_rate": 4.2},
                {"branch_zh": "拒绝客群", "branch_en": "Rejected", "pct": 12, "bad_rate": None},
            ],
        },
    },
    "v2.4-Beta": {
        "id": "v2.4-Beta",
        "nickname": "黑五大促 Overlimit 策略",
        "name": "Beta v2.4",
        "role": "beta",
        "desc_zh": "ML驱动激进扩张策略。无硬性评分门槛，DTI 最高容忍 0.75，额度提升最高 +120%。通过率最高，但行为模型对 18-25 岁薄文件客群的通过率偏低，DI Ratio 低于合规红线 0.80。",
        "desc_en": "ML-driven aggressive expansion. No hard score cutoff, DTI up to 0.75, limit increase up to +120%. Highest approval rate, but the behavioural model under-approves thin-file 18-25 applicants, pushing their DI Ratio below the 0.80 compliance threshold.",
        "score_cutoff": None,
        "dti_limit": 0.75,
        "mob_months": 6,
        "mob_dpd_max": None,
        "limit_increase_min": 0.30,
        "limit_increase_max": 1.20,
        "anti_fraud": "ml_realtime",
        "rules": {
            "anti_fraud_rules": [
                {"rule": "ml_fraud_score", "desc_zh": "ML实时欺诈评分 ≥ 70", "desc_en": "ML real-time fraud score ≥ 70"},
                {"rule": "network_analysis", "desc_zh": "关联网络异常检测", "desc_en": "Network anomaly detection"},
                {"rule": "device_fingerprint", "desc_zh": "设备指纹+位置验证", "desc_en": "Device fingerprint + location"},
            ],
            "if_else": [
                {"condition": "dti > 0.75", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "ml_fraud_score < 70", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "mob6_roll_avg > 1%", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "ml_decile >= 8", "action_zh": "提额 120%", "action_en": "Increase 120%"},
                {"condition": "ml_decile >= 6", "action_zh": "提额 80%~100%", "action_en": "Increase 80%~100%"},
                {"condition": "ml_decile >= 4", "action_zh": "提额 30%~60%", "action_en": "Increase 30%~60%"},
            ],
            "scorecard_features": [
                {"feature": "行为数据", "weight": 30, "direction": "positive"},
                {"feature": "月负债率", "weight": 28, "direction": "negative"},
                {"feature": "消费模式", "weight": 20, "direction": "positive"},
                {"feature": "还款习惯", "weight": 15, "direction": "positive"},
                {"feature": "年龄", "weight": 7, "direction": "positive"},
            ],
            "decision_table": [
                {"dti_band": "≤0.40", "score_band": "decile 8-10", "action_zh": "提额120%", "action_en": "+120%", "rate": "9.5%"},
                {"dti_band": "≤0.40", "score_band": "decile 6-7", "action_zh": "提额80%", "action_en": "+80%", "rate": "11.0%"},
                {"dti_band": "0.40-0.75", "score_band": "decile 8-10", "action_zh": "提额80%", "action_en": "+80%", "rate": "10.5%"},
                {"dti_band": "0.40-0.75", "score_band": "decile 4-7", "action_zh": "提额40%", "action_en": "+40%", "rate": "13.0%"},
                {"dti_band": ">0.75", "score_band": "any", "action_zh": "拒绝", "action_en": "Reject", "rate": "—"},
            ],
            "bifurcation": [
                {"branch_zh": "高分值低负债 ML Top30%", "branch_en": "ML Top30% Low-DTI", "pct": 35, "bad_rate": 1.8},
                {"branch_zh": "中分值扩张客群 ML 30-60%", "branch_en": "ML Mid Expansion", "pct": 40, "bad_rate": 3.5},
                {"branch_zh": "边际客群 ML 60-70%", "branch_en": "ML Marginal", "pct": 15, "bad_rate": 5.8},
                {"branch_zh": "拒绝客群", "branch_en": "Rejected", "pct": 10, "bad_rate": None},
            ],
        },
    },
    "v2.5-RC": {
        "id": "v2.5-RC",
        "nickname": "黑五大促 Overlimit 策略",
        "name": "RC v2.5",
        "role": "beta",
        "desc_zh": "图网络反欺诈+新评分卡。评分门槛 ≥640，DTI 上限 0.70，MOB9 零逾期，额度提升最高 +100%。风险调整后收益仅次于 v2.3。",
        "desc_en": "Graph network anti-fraud + new scorecard. Score ≥640, DTI ≤0.70, MOB9 zero delinquency, limit increase up to +100%. Risk-adjusted return second only to v2.3.",
        "score_cutoff": 640,
        "dti_limit": 0.70,
        "mob_months": 9,
        "mob_dpd_max": 0,
        "limit_increase_min": 0.25,
        "limit_increase_max": 1.00,
        "anti_fraud": "graph_network",
        "rules": {
            "anti_fraud_rules": [
                {"rule": "graph_network", "desc_zh": "图网络欺诈团伙识别", "desc_en": "Graph network fraud ring detection"},
                {"rule": "consortium_lookup", "desc_zh": "联合征信查询", "desc_en": "Consortium credit lookup"},
                {"rule": "behavior_score", "desc_zh": "行为评分 ≥ 55", "desc_en": "Behavior score ≥ 55"},
            ],
            "if_else": [
                {"condition": "score < 640", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "dti > 0.70", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "mob9_dpd > 0", "action_zh": "拒绝", "action_en": "Reject"},
                {"condition": "score >= 720", "action_zh": "提额 100%", "action_en": "Increase 100%"},
                {"condition": "score >= 680", "action_zh": "提额 60%~80%", "action_en": "Increase 60%~80%"},
                {"condition": "score >= 640", "action_zh": "提额 25%~50%", "action_en": "Increase 25%~50%"},
            ],
            "scorecard_features": [
                {"feature": "月负债率", "weight": 30, "direction": "negative"},
                {"feature": "多头借贷数", "weight": 23, "direction": "negative"},
                {"feature": "信用局v2特征", "weight": 20, "direction": "positive"},
                {"feature": "工作年限", "weight": 15, "direction": "positive"},
                {"feature": "年龄", "weight": 12, "direction": "positive"},
            ],
            "decision_table": [
                {"dti_band": "≤0.40", "score_band": "≥720", "action_zh": "提额100%", "action_en": "+100%", "rate": "10.0%"},
                {"dti_band": "≤0.40", "score_band": "680-719", "action_zh": "提额70%", "action_en": "+70%", "rate": "11.5%"},
                {"dti_band": "≤0.40", "score_band": "640-679", "action_zh": "提额45%", "action_en": "+45%", "rate": "13.0%"},
                {"dti_band": "0.40-0.70", "score_band": "≥720", "action_zh": "提额65%", "action_en": "+65%", "rate": "11.0%"},
                {"dti_band": "0.40-0.70", "score_band": "680-719", "action_zh": "提额45%", "action_en": "+45%", "rate": "12.5%"},
                {"dti_band": "0.40-0.70", "score_band": "640-679", "action_zh": "提额25%", "action_en": "+25%", "rate": "14.0%"},
                {"dti_band": ">0.70", "score_band": "any", "action_zh": "拒绝", "action_en": "Reject", "rate": "—"},
            ],
            "bifurcation": [
                {"branch_zh": "高质量扩张 (score≥720, dti≤0.40)", "branch_en": "Quality Expansion", "pct": 30, "bad_rate": 1.5},
                {"branch_zh": "平衡扩张 (680-720, dti≤0.70)", "branch_en": "Balanced Expansion", "pct": 42, "bad_rate": 2.9},
                {"branch_zh": "边际扩张 (640-680, dti≤0.70)", "branch_en": "Marginal Expansion", "pct": 18, "bad_rate": 4.5},
                {"branch_zh": "拒绝客群", "branch_en": "Rejected", "pct": 10, "bad_rate": None},
            ],
        },
    },
}

SAMPLES = [
    {
        "id": "consumer_2024q1q2",
        "name_zh": "黑五主样本 2024Q1-Q2",
        "name_en": "Black Friday Main Sample 2024 Q1-Q2",
        "vintage": "2024Q1-Q2",
        "product_mix_zh": "信用卡提额 70% + 消费贷提额 30%",
        "product_mix_en": "Credit card 70% + Consumer loan 30%",
        "channels_zh": "App自申 / 短信触达 / 线下网点 / 合作平台",
        "channels_en": "App / SMS / Branch / Partner",
        "n_rows": 180000,
        "lookback_months": 6,
        "perf_window_months": 12,
        "desc_zh": "大促主样本，含4渠道5地区完整决策日志，统计性质稳定",
        "desc_en": "Main promotion sample, 4 channels, 5 regions, complete decision logs",
    },
    {
        "id": "consumer_2024q1",
        "name_zh": "黑五线下样本 2024Q1",
        "name_en": "Black Friday Branch Sample 2024 Q1",
        "vintage": "2024Q1",
        "product_mix_zh": "信用卡提额 65% + 消费贷提额 35%",
        "product_mix_en": "Credit card 65% + Consumer loan 35%",
        "channels_zh": "线下网点 / 短信触达",
        "channels_en": "Branch / SMS",
        "n_rows": 86000,
        "lookback_months": 3,
        "perf_window_months": 6,
        "desc_zh": "线下渠道样本，客户质量略优，坏账率低 0.7pp",
        "desc_en": "Branch channel sample, slightly better quality, bad rate 0.7pp lower",
    },
]

# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

SCORE_MEAN = 648.0
SCORE_STD = 58.0

# Feature centring/scaling and risk coefficients. The same linear predictor
# defines both the ground-truth PD (generate_synthetic_data) and each model's
# estimate (_model_score), so the model is genuinely predictive and metrics are
# computed, never hardcoded.
_NUM_LOANS_MEAN, _NUM_LOANS_STD = 1.3, 1.3
_NUM_INQ_MEAN, _NUM_INQ_STD = 1.6, 1.6
_TENURE_MEAN, _TENURE_STD = 5.3, 3.5

# Scorecard features: (data column, display name, risk direction).
# direction "positive" = higher value lowers risk (good); "negative" = raises risk.
_SCORECARD_FEATURES = [
    ("score", "信用评分", "positive"),
    ("dti", "月负债率", "negative"),
    ("num_loans", "多头借贷数", "negative"),
    ("num_inquiries", "信用查询数", "negative"),
    ("tenure", "工作年限", "positive"),
]


def _risk_logit(score, dti, num_loans, num_inquiries, tenure, age_band) -> np.ndarray:
    """Latent default-risk log-odds as a function of the scorecard features."""
    score_z = (score - SCORE_MEAN) / SCORE_STD
    dti_z = (dti - 0.40) / 0.18
    loans_z = (num_loans - _NUM_LOANS_MEAN) / _NUM_LOANS_STD
    inq_z = (num_inquiries - _NUM_INQ_MEAN) / _NUM_INQ_STD
    tenure_z = (tenure - _TENURE_MEAN) / _TENURE_STD
    young = (age_band == 0).astype(np.float32)
    return (-3.18 - 1.25 * score_z + 1.20 * dti_z + 0.55 * loans_z
            + 0.42 * inq_z - 0.40 * tenure_z + 0.35 * young)


def generate_synthetic_data(n: int = 50000, seed: int = 42) -> np.ndarray:
    """Generate synthetic customer records as a structured numpy array.

    The generative model is calibrated so that the *real* metrics computed
    downstream (approval rate, bad rate, AUC/KS, RAROC, DI ratio) land in
    realistic, correctly-ordered ranges without any post-hoc overrides.
    """
    rng = np.random.default_rng(seed)

    # Credit score: Normal(648, 58), clipped [520, 840]. The mean sits below
    # the strategy cutoffs (640-680) so those cutoffs actually bind.
    score = np.clip(rng.normal(SCORE_MEAN, SCORE_STD, n), 520, 840).astype(np.float32)

    # DTI (月负债率): Beta(2.4, 4.2) scaled to [0.10, 0.88]
    dti_raw = rng.beta(2.4, 4.2, n)
    dti = (dti_raw * (0.88 - 0.10) + 0.10).astype(np.float32)

    # Credit-bureau scorecard inputs
    num_loans = rng.poisson(1.3, n).clip(0, 9).astype(np.int8)          # 多头借贷数
    num_inquiries = rng.poisson(1.6, n).clip(0, 12).astype(np.int8)     # 信用查询数 (近6月)
    tenure = rng.gamma(2.2, 2.4, n).clip(0, 25).astype(np.float32)      # 工作年限

    # Age bands: 18-25(8%), 26-35(32%), 36-45(35%), 46-55(18%), 56+(7%)
    age_band = rng.choice(5, n, p=[0.08, 0.32, 0.35, 0.18, 0.07]).astype(np.int8)
    age_band_mid = np.array([22, 30, 40, 50, 60], dtype=np.float32)
    age = age_band_mid[age_band] + rng.uniform(-2, 2, n).astype(np.float32)

    # Gender: 0=male(58%), 1=female(42%)
    gender = rng.choice(2, n, p=[0.58, 0.42]).astype(np.int8)

    # Channel: 0=online(52%), 1=branch(30%), 2=partner(18%)
    channel = rng.choice(3, n, p=[0.52, 0.30, 0.18]).astype(np.int8)

    # Vintage quarter: 0=2023Q3(15%), 1=2023Q4(22%), 2=2024Q1(35%), 3=2024Q2(28%)
    vintage_q = rng.choice(4, n, p=[0.15, 0.22, 0.35, 0.28]).astype(np.int8)

    # Latent PD from the scorecard features (same predictor the models estimate)
    logit_pd = _risk_logit(score, dti, num_loans, num_inquiries, tenure, age_band)
    pd_true = 1.0 / (1.0 + np.exp(-logit_pd))

    # Realised MOB12 bad flag
    bad = (rng.uniform(0, 1, n) < pd_true).astype(np.int8)

    # Trailing-delinquency recency: months since last delinquency event
    # (99 = no event in window). Riskier customers are likelier to have a
    # recent event, so the "zero-delinquency over MOB-k" rules bite differently
    # across strategies. This realises the MOB rules the strategies describe.
    p_del = np.clip(0.16 + 0.70 * pd_true, 0.0, 0.80)
    had_event = rng.uniform(0, 1, n) < p_del
    months_clean = np.where(had_event, rng.integers(0, 15, n), 99).astype(np.int8)

    dt = np.dtype([
        ("score", np.float32),
        ("dti", np.float32),
        ("num_loans", np.int8),
        ("num_inquiries", np.int8),
        ("tenure", np.float32),
        ("age", np.float32),
        ("age_band", np.int8),
        ("gender", np.int8),
        ("channel", np.int8),
        ("vintage_q", np.int8),
        ("months_clean", np.int8),
        ("pd_true", np.float32),
        ("bad", np.int8),
    ])
    result = np.empty(n, dtype=dt)
    result["score"] = score
    result["dti"] = dti
    result["num_loans"] = num_loans
    result["num_inquiries"] = num_inquiries
    result["tenure"] = tenure
    result["age"] = age
    result["age_band"] = age_band
    result["gender"] = gender
    result["channel"] = channel
    result["vintage_q"] = vintage_q
    result["months_clean"] = months_clean
    result["pd_true"] = pd_true.astype(np.float32)
    result["bad"] = bad
    return result


# ---------------------------------------------------------------------------
# Strategy approval mask
# ---------------------------------------------------------------------------

# Target approval rate per strategy (on the reference population). Each
# strategy's model-score cutoff is calibrated to hit this rate, so the cutoff
# is a real model threshold rather than a hardcoded number.
_PD_TARGET = {"v2.2": 0.23, "v2.3": 0.44, "v2.4-Beta": 0.66, "v2.5-RC": 0.49}
_PD_THRESHOLD_CACHE: dict[str, float] = {}


def _eligible_mask(df: np.ndarray, strategy_id: str) -> np.ndarray:
    """Hard policy gates (independent of the model score): DTI cap, zero
    delinquency over the MOB window, and v2.4-Beta's behaviour/thin-file gate
    that screens out ~40% of young applicants (its genuine DI source)."""
    s = STRATEGIES[strategy_id]
    mask = df["dti"] <= s["dti_limit"]
    if s.get("mob_dpd_max") == 0:
        mask = mask & (df["months_clean"] >= s["mob_months"])
    if strategy_id == "v2.4-Beta":
        rng = np.random.default_rng(7)
        young = df["age_band"] == 0
        thin_keep = np.ones(len(df), dtype=bool)
        thin_keep[young] = rng.uniform(0, 1, int(young.sum())) < 0.60
        mask = mask & thin_keep
    return mask


def _pd_threshold(strategy_id: str) -> float:
    """Model-score (pd̂) cutoff calibrated on the reference population to hit the
    strategy's target approval rate. Cached per process."""
    if strategy_id not in _PD_THRESHOLD_CACHE:
        ref = generate_synthetic_data(n=50000, seed=42)
        elig = _eligible_mask(ref, strategy_id)
        pd_elig = np.sort(_model_score(ref, strategy_id)[elig])
        target_n = int(_PD_TARGET.get(strategy_id, 0.4) * len(ref))
        if len(pd_elig) == 0:
            _PD_THRESHOLD_CACHE[strategy_id] = 1.0
        else:
            k = min(target_n, len(pd_elig) - 1)
            _PD_THRESHOLD_CACHE[strategy_id] = float(pd_elig[k])
    return _PD_THRESHOLD_CACHE[strategy_id]


def _approve_mask(df: np.ndarray, strategy_id: str) -> np.ndarray:
    """Approve customers the strategy's own model ranks as lowest-risk
    (pd̂ ≤ calibrated cutoff), subject to the hard policy gates. Because each
    strategy uses a different model, the approved sets genuinely disagree in
    both directions (swap-in AND swap-out), not just as nested supersets.
    """
    return _eligible_mask(df, strategy_id) & (_model_score(df, strategy_id) <= _pd_threshold(strategy_id))


# ---------------------------------------------------------------------------
# Simulated model score (different per strategy)
# ---------------------------------------------------------------------------

# Per-version model noise: smaller = the estimate tracks the latent risk more
# tightly (sharper discrimination, better calibration). v2.3 is the best model.
_MODEL_NOISE = {"v2.2": 1.45, "v2.3": 0.70, "v2.4-Beta": 1.15, "v2.5-RC": 0.85}


def _model_score(df: np.ndarray, strategy_id: str) -> np.ndarray:
    """Return each strategy's estimated probability of default (bad).

    The estimate is the true risk logit plus version-specific Gaussian noise, so
    it stays calibrated to the real bad rate (predicted ≈ actual) while better
    versions discriminate more sharply (less noise → higher AUC/KS).
    """
    logit = _risk_logit(
        df["score"], df["dti"], df["num_loans"], df["num_inquiries"],
        df["tenure"], df["age_band"],
    )
    sigma = _MODEL_NOISE.get(strategy_id, 1.0)
    rng = np.random.default_rng(int(hashlib.md5(strategy_id.encode()).hexdigest(), 16) % (2**32))
    noise = rng.normal(0, sigma, len(df))
    pd_hat = 1.0 / (1.0 + np.exp(-(logit + noise)))
    return pd_hat.astype(np.float32)


# ---------------------------------------------------------------------------
# L1: Model quality metrics
# ---------------------------------------------------------------------------

def _compute_l1(df: np.ndarray, strategy_id: str, approved: np.ndarray) -> dict:
    sub = df[approved]
    if len(sub) < 100:
        return {}

    y_true = sub["bad"].astype(int)
    # _model_score returns the estimated probability of default (bad=1)
    y_pred_prob = _model_score(sub, strategy_id)

    # AUC
    auc = float(roc_auc_score(y_true, y_pred_prob)) if y_true.sum() > 0 else 0.5

    # KS statistic
    pos_scores = y_pred_prob[y_true == 1]
    neg_scores = y_pred_prob[y_true == 0]
    ks_stat, _ = stats.ks_2samp(pos_scores, neg_scores)

    # Brier score
    brier = float(brier_score_loss(y_true, y_pred_prob))

    # Lift@20%: top 20% of predicted probability
    threshold_idx = int(len(y_pred_prob) * 0.80)  # top 20% means >= 80th percentile
    threshold_val = np.sort(y_pred_prob)[threshold_idx]
    top20_mask = y_pred_prob >= threshold_val
    overall_rate = y_true.mean()
    top20_rate = y_true[top20_mask].mean() if top20_mask.sum() > 0 else 0.0
    lift_at_20 = float(top20_rate / overall_rate) if overall_rate > 0 else 1.0

    # ROC curve (20 points)
    fpr, tpr, _ = roc_curve(y_true, y_pred_prob)
    # Downsample to 20 points
    indices = np.linspace(0, len(fpr) - 1, 20, dtype=int)
    roc_points = [
        {"fpr": round(float(fpr[i]), 4), "tpr": round(float(tpr[i]), 4)}
        for i in indices
    ]

    # PSI monthly trend (6 months simulated)
    # Simulate PSI values month-over-month as small deviations
    rng_psi = np.random.default_rng(int(hashlib.md5(strategy_id.encode()).hexdigest(), 16) % (2**32))
    psi_base = 0.04 if strategy_id == "v2.2" else (0.06 if strategy_id == "v2.3" else 0.09)
    psi_trend = [
        {"month": f"M{i+1}", "psi": round(float(psi_base + rng_psi.normal(0, 0.008)), 4)}
        for i in range(6)
    ]

    # Calibration curve (10 bins)
    bin_edges = np.linspace(0, 1, 11)
    calib_points = []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (y_pred_prob >= lo) & (y_pred_prob < hi)
        if mask.sum() > 0:
            calib_points.append({
                "predicted": round(float(y_pred_prob[mask].mean()), 4),
                "actual": round(float(y_true[mask].mean()), 4),
                "count": int(mask.sum()),
            })

    return {
        "auc": round(auc, 4),
        "ks": round(float(ks_stat), 4),
        "lift_at_20": round(lift_at_20, 3),
        "brier_score": round(brier, 4),
        "roc_curve": roc_points,
        "psi_trend": psi_trend,
        "calibration": calib_points,
        "n_approved": int(approved.sum()),
    }


# ---------------------------------------------------------------------------
# L2: Business value metrics
# ---------------------------------------------------------------------------

# Risk-based pricing margin per strategy (a business pricing assumption, not a
# risk metric): better-discriminating strategies price risk more sharply and
# capture more net interest margin on the incremental balance.
_PRICING_MARGIN = {"v2.2": 0.150, "v2.3": 0.182, "v2.4-Beta": 0.168, "v2.5-RC": 0.176}
_LGD = 0.55
_CAPITAL_RATIO = 0.72  # scales (margin - EL) into a realistic RAROC band


def _compute_l2(df: np.ndarray, strategy_id: str, approved: np.ndarray) -> dict:
    n_total = len(df)
    n_approved = int(approved.sum())
    approval_rate = round(n_approved / n_total, 4)

    sub = df[approved]
    bad_rate = round(float(sub["bad"].mean()), 4) if len(sub) > 0 else 0.0

    s = STRATEGIES[strategy_id]
    avg_increase = (s["limit_increase_min"] + s["limit_increase_max"]) / 2.0
    margin_rate = _PRICING_MARGIN.get(strategy_id, 0.165)

    avg_loan = 8000.0
    incremental_balance = avg_loan * avg_increase
    revenue_per = incremental_balance * margin_rate
    el_per = incremental_balance * bad_rate * _LGD
    profit_per = revenue_per - el_per

    # RAROC is computed from the *real* bad rate and the strategy's pricing
    # margin, so it responds to data (e.g. when a slice changes the bad rate).
    raroc = round((margin_rate - bad_rate * _LGD) / _CAPITAL_RATIO, 4)

    economic_capital = incremental_balance * n_approved * 0.10
    el_total = el_per * n_approved

    # Pareto frontier: profit-per-account declines as the book is expanded past
    # the strategy's operating point (marginal approvals are riskier).
    pareto = []
    for pct in np.linspace(0.10, 0.70, 15):
        extra = max((pct - approval_rate) / 0.50, 0.0)
        adj_profit = profit_per * (1 - 0.30 * extra)
        pareto.append({"approval_rate": round(float(pct), 3), "avg_profit": round(float(adj_profit), 2)})

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
        "rejection_reasons": compute_rejection_reasons(df, strategy_id),
        "raroc_bands": compute_raroc_bands(df, strategy_id),
    }


# ---------------------------------------------------------------------------
# L3: Risk metrics
# ---------------------------------------------------------------------------

def _compute_l3(df: np.ndarray, strategy_id: str, approved: np.ndarray) -> dict:
    # MOB12 bad rate is the real realised bad rate on the approved book; the
    # remaining risk indicators are derived deterministically from it (this
    # synthetic dataset has no true longitudinal/first-payment structure, so
    # FPD and roll rates are modelled as stable functions of the bad rate and
    # therefore still respond to slicing).
    sub = df[approved]
    bad_rate = round(float(sub["bad"].mean()), 4) if len(sub) > 0 else 0.0
    # First-payment default runs well below the MOB12 bad rate.
    fpd_rate = round(max(bad_rate * 0.32, 0.001), 4)

    # Roll rates (M0→M1→M2→M3+): M0→M1 tracks the bad rate; later transitions
    # are progressively higher conditional roll probabilities.
    m0m1 = round(min(0.020 + bad_rate * 1.1, 0.14), 4)
    roll_rates = {
        "m0_to_m1": m0m1,
        "m1_to_m2": round(0.52 + bad_rate * 3.5, 4),
        "m2_to_m3plus": round(0.60 + bad_rate * 3.0, 4),
    }

    # Vintage curve (12 months): cumulative bad rate ramp-up
    vintage_curve = []
    peak = bad_rate
    for m in range(1, 13):
        # Logistic ramp: slow start, fast mid, plateau
        cum_rate = peak * (1 / (1 + np.exp(-0.7 * (m - 6))))
        vintage_curve.append({"month": m, "cum_bad_rate": round(float(cum_rate), 4)})

    # FPD monthly trend (6 months)
    rng_fpd = np.random.default_rng(int(hashlib.md5((strategy_id + "_fpd").encode()).hexdigest(), 16) % (2**32))
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


# ---------------------------------------------------------------------------
# L4: Swap-set analysis
# ---------------------------------------------------------------------------

def _compute_l4(
    df: np.ndarray,
    challenger_id: str,
    champion_id: str,
) -> dict:
    """Compare challenger vs champion decision quadrants."""
    chall_mask = _approve_mask(df, challenger_id)
    champ_mask = _approve_mask(df, champion_id)

    double_approve_mask = chall_mask & champ_mask
    swap_in_mask = chall_mask & ~champ_mask    # challenger approves, champion rejects
    swap_out_mask = ~chall_mask & champ_mask   # challenger rejects, champion approves
    double_reject_mask = ~chall_mask & ~champ_mask

    bad = df["bad"].astype(int)

    def _br(mask: np.ndarray) -> float:
        sub = bad[mask]
        return float(sub.mean()) if len(sub) > 0 else 0.0

    da_n = int(double_approve_mask.sum())
    si_n = int(swap_in_mask.sum())
    so_n = int(swap_out_mask.sum())
    dr_n = int(double_reject_mask.sum())
    total = len(df)

    consistency_pct = round((da_n + dr_n) / total, 4)

    # Baseline (champion) approved bad rate, and how much riskier the customers
    # the champion approved but the challenger drops (swap-out) are vs that base.
    base_bad_rate = _br(champ_mask)
    swap_out_bad_rate = _br(swap_out_mask)
    swap_out_lift = round(swap_out_bad_rate / base_bad_rate, 2) if base_bad_rate > 0 else 0.0

    # Two-proportion z-test: is the swap-in bad rate different from the
    # double-approve (jointly accepted) bad rate?
    p_value = _two_proportion_pvalue(
        bad[swap_in_mask], bad[double_approve_mask]
    )

    # Score-band consistency breakdown
    score_bands = [
        ("≤640", 520, 640),
        ("641-680", 641, 680),
        ("681-720", 681, 720),
        (">720", 720, 840),
    ]
    band_consistency = []
    for label, lo, hi in score_bands:
        band_mask = (df["score"] >= lo) & (df["score"] <= hi)
        if band_mask.sum() == 0:
            continue
        agree = ((chall_mask == champ_mask) & band_mask).sum()
        band_consistency.append({
            "score_band": label,
            "n": int(band_mask.sum()),
            "consistency_pct": round(float(agree / band_mask.sum()), 4),
        })

    return {
        "double_approve": {"n": da_n, "pct": round(da_n / total, 4), "bad_rate": round(_br(double_approve_mask), 4)},
        "swap_in": {"n": si_n, "pct": round(si_n / total, 4), "bad_rate": round(_br(swap_in_mask), 4)},
        "swap_out": {"n": so_n, "pct": round(so_n / total, 4), "bad_rate": round(_br(swap_out_mask), 4)},
        "double_reject": {"n": dr_n, "pct": round(dr_n / total, 4), "bad_rate": 0.0},
        "consistency_pct": consistency_pct,
        "score_band_consistency": band_consistency,
        "base_bad_rate": round(base_bad_rate, 4),
        "swap_out_lift": swap_out_lift,
        "p_value": p_value,
        "challenger": challenger_id,
        "champion": champion_id,
    }


def _two_proportion_pvalue(a: np.ndarray, b: np.ndarray) -> float:
    """Two-sided two-proportion z-test p-value for P(bad) in groups a vs b."""
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


# ---------------------------------------------------------------------------
# L5: Fairness metrics
# ---------------------------------------------------------------------------

def _compute_l5(df: np.ndarray, strategy_id: str, approved: np.ndarray) -> dict:
    """Compute DI Ratio, TPR gap, and feature importance for fairness layer."""
    bad = df["bad"].astype(int)

    def _di_ratio(group_mask: np.ndarray, ref_mask: np.ndarray) -> float:
        """DI = approval_rate(group) / approval_rate(reference)."""
        group_apr = approved[group_mask].mean() if group_mask.sum() > 0 else 0.0
        ref_apr = approved[ref_mask].mean() if ref_mask.sum() > 0 else 1.0
        return float(group_apr / ref_apr) if ref_apr > 0 else 1.0

    def _tpr_gap(group_mask: np.ndarray, ref_mask: np.ndarray) -> float:
        """TPR gap = TPR(group) - TPR(reference)."""
        def _tpr(m: np.ndarray) -> float:
            sub_bad = bad[m & (bad == 1)]
            sub_appr_bad = bad[m & approved.astype(bool) & (bad == 1)]
            return float(len(sub_appr_bad) / len(sub_bad)) if len(sub_bad) > 0 else 0.0
        return round(_tpr(group_mask) - _tpr(ref_mask), 4)

    # Gender: female (1) vs male (0)
    female_mask = df["gender"] == 1
    male_mask = df["gender"] == 0

    # Age: young 18-25 (band=0) vs core 26-55 (band 1-3)
    young_mask = df["age_band"] == 0
    core_mask = (df["age_band"] >= 1) & (df["age_band"] <= 3)

    # Channel: partner (2) vs online (0)
    partner_mask = df["channel"] == 2
    online_mask = df["channel"] == 0

    di_female_male = _di_ratio(female_mask, male_mask)
    di_young_core = _di_ratio(young_mask, core_mask)
    di_partner_online = _di_ratio(partner_mask, online_mask)

    di_groups = [
        {
            "group": "female_vs_male",
            "group_zh": "女性 vs 男性",
            "group_en": "Female vs Male",
            "di_ratio": round(di_female_male, 3),
            "compliant": di_female_male >= 0.80,
            "threshold": 0.80,
        },
        {
            "group": "young_vs_core",
            "group_zh": "18-25岁 vs 核心客群",
            "group_en": "Age 18-25 vs Core",
            "di_ratio": round(di_young_core, 3),
            "compliant": di_young_core >= 0.80,
            "threshold": 0.80,
        },
        {
            "group": "partner_vs_online",
            "group_zh": "合作平台 vs 线上",
            "group_en": "Partner vs Online",
            "di_ratio": round(di_partner_online, 3),
            "compliant": di_partner_online >= 0.80,
            "threshold": 0.80,
        },
    ]

    tpr_gaps = [
        {"group": "female_vs_male", "tpr_gap": _tpr_gap(female_mask, male_mask)},
        {"group": "young_vs_core", "tpr_gap": _tpr_gap(young_mask, core_mask)},
        {"group": "partner_vs_online", "tpr_gap": _tpr_gap(partner_mask, online_mask)},
    ]

    has_compliance_issue = any(not g["compliant"] for g in di_groups)

    return {
        "di_ratios": di_groups,
        "tpr_gaps": tpr_gaps,
        "feature_importance": compute_feature_importance(df, strategy_id, approved),
        "has_compliance_issue": has_compliance_issue,
        "compliance_threshold": 0.80,
    }


# ---------------------------------------------------------------------------
# Real attribution / decomposition computations
# ---------------------------------------------------------------------------

def compute_feature_importance(
    df: np.ndarray, strategy_id: str, approved: Optional[np.ndarray] = None
) -> list[dict]:
    """Permutation feature importance of the scorecard inputs.

    For each feature, shuffle it on the approved book and measure the drop in
    the model's AUC; normalise the drops to sum to 1. Signed by risk direction.
    """
    if approved is None:
        approved = _approve_mask(df, strategy_id)
    sub = df[approved]
    n_feat = len(_SCORECARD_FEATURES)

    y = sub["bad"].astype(int)
    if len(sub) < 200 or y.sum() == 0 or len(np.unique(y)) < 2:
        eq = round(1.0 / n_feat, 4)
        return [{"feature": nm, "importance": eq, "direction": d}
                for _, nm, d in _SCORECARD_FEATURES]

    base_auc = roc_auc_score(y, _model_score(sub, strategy_id))
    rng = np.random.default_rng(
        int(hashlib.md5((strategy_id + "_imp").encode()).hexdigest(), 16) % (2**32)
    )
    drops = []
    for col, _name, _dir in _SCORECARD_FEATURES:
        perm = sub.copy()
        vals = perm[col].copy()
        rng.shuffle(vals)
        perm[col] = vals
        drops.append(max(base_auc - roc_auc_score(y, _model_score(perm, strategy_id)), 0.0))

    total = sum(drops) or 1.0
    return [
        {"feature": name, "importance": round(drop / total, 4), "direction": direction}
        for (col, name, direction), drop in zip(_SCORECARD_FEATURES, drops)
    ]


def compute_rejection_reasons(df: np.ndarray, strategy_id: str) -> list[dict]:
    """Distribution of the *primary* reason each rejected applicant was declined,
    derived from the strategy's actual rules (priority-ordered attribution)."""
    s = STRATEGIES[strategy_id]
    approved = _approve_mask(df, strategy_id)
    rejected = ~approved
    n_rej = int(rejected.sum())
    if n_rej == 0:
        return []

    remaining = rejected.copy()
    tally: list[tuple[str, int]] = []

    def _take(cond: np.ndarray, label: str) -> None:
        nonlocal remaining
        hit = remaining & cond
        c = int(hit.sum())
        if c > 0:
            tally.append((label, c))
        remaining = remaining & ~cond

    # Hard policy gates first, then the model-score cutoff
    _take(df["dti"] > s["dti_limit"], "负债率过高")
    if s.get("mob_dpd_max") == 0:
        _take(df["months_clean"] < s["mob_months"], "近期逾期记录")
    if strategy_id == "v2.4-Beta":
        _take(df["age_band"] == 0, "薄文件/行为不足")
    _take(_model_score(df, strategy_id) > _pd_threshold(strategy_id), "风险评分不足")

    rest = int(remaining.sum())
    if rest > 0:
        tally.append(("其他", rest))

    tally.sort(key=lambda x: -x[1])
    return [{"reason": r, "pct": round(c / n_rej * 100, 1)} for r, c in tally]


def compute_raroc_bands(df: np.ndarray, strategy_id: str) -> list[dict]:
    """RAROC by credit-score band, computed from the realised bad rate in each
    band and the strategy's pricing margin. Low bands turn negative — the reason
    they sit below the approval cutoff."""
    margin = _PRICING_MARGIN.get(strategy_id, 0.165)
    bands = [("<600", 520, 600), ("600-650", 600, 650), ("650-700", 650, 700),
             ("700-750", 700, 750), ("750+", 750, 841)]
    pop_bad = float(df["bad"].mean())
    out = []
    for label, lo, hi in bands:
        m = (df["score"] >= lo) & (df["score"] < hi)
        sub = df[m]
        br = float(sub["bad"].mean()) if len(sub) >= 50 else pop_bad
        raroc = (margin - br * _LGD) / _CAPITAL_RATIO
        out.append({"band": label, "raroc": round(raroc * 100, 1)})
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_strategy(df: np.ndarray, strategy_id: str, champion_id: str = "v2.2") -> dict:
    """
    Compute all L1-L5 metrics for a given strategy against the data.

    Returns a dict with keys: l1, l2, l3, l4, l5, strategy_info
    """
    if strategy_id not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_id}")

    approved = _approve_mask(df, strategy_id)

    l1 = _compute_l1(df, strategy_id, approved)
    l2 = _compute_l2(df, strategy_id, approved)
    l3 = _compute_l3(df, strategy_id, approved)
    l4 = _compute_l4(df, strategy_id, champion_id)
    l5 = _compute_l5(df, strategy_id, approved)

    return {
        "strategy_info": STRATEGIES[strategy_id],
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "l4": l4,
        "l5": l5,
    }
