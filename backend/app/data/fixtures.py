from __future__ import annotations

import hashlib
import json

from app.config import settings
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
        "desc_zh": "当前线上基线策略，稳定运行 18 个月。按评分卡 PD 择优准入（约 23% 通过率，准入线 ≈ 评分 680），严格 DTI 控制（≤0.60），MOB12 零逾期，额度提升区间 +20%~+50%。",
        "desc_en": "Current production baseline, stable for 18 months. Approves the lowest-PD applicants by scorecard (~23% approval, cutoff ≈ score 680), strict DTI (≤0.60), MOB12 zero-delinquency, limit increase +20%~+50%.",
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
        "desc_zh": "重训模型+联合反欺诈。判别力最强的评分卡，准入适度放开（约 44% 通过率，准入线 ≈ 评分 650），DTI 上限 0.68，MOB6 零逾期，额度提升最高 +80%。RAROC 最优策略。",
        "desc_en": "Retrained model + consortium anti-fraud. Sharpest scorecard; approval eased (~44%, cutoff ≈ score 650), DTI ≤0.68, MOB6 zero-delinquency, limit increase up to +80%. Best RAROC strategy.",
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
        "desc_zh": "ML驱动激进扩张策略。模型准入最宽松（约 66% 通过率），DTI 最高容忍 0.75，无 MOB 逾期硬门槛，额度提升最高 +120%。通过率最高，但行为模型对 18-25 岁薄文件客群通过率偏低，DI Ratio 跌破合规红线 0.80（约 0.53）。",
        "desc_en": "ML-driven aggressive expansion. Loosest model approval (~66%), DTI up to 0.75, no hard MOB delinquency gate, limit increase up to +120%. Highest approval rate, but the behavioural model under-approves thin-file 18-25 applicants, pushing their DI Ratio below the 0.80 line (~0.53).",
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
        "desc_zh": "图网络反欺诈+新评分卡。模型准入约 49% 通过率（准入线 ≈ 评分 640），DTI 上限 0.70，MOB9 零逾期，额度提升最高 +100%。风险调整后收益仅次于 v2.3。",
        "desc_en": "Graph-network anti-fraud + new scorecard. Model approval ~49% (cutoff ≈ score 640), DTI ≤0.70, MOB9 zero-delinquency, limit increase up to +100%. Risk-adjusted return second only to v2.3.",
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

    # ── Time axis ────────────────────────────────────────────────────────
    # Booking month 0..11 inside the quarter the account belongs to. This is
    # what makes PSI/CSI and the whole of L3 measurable instead of simulated.
    book_month = (vintage_q.astype(np.int16) * 3 + rng.integers(0, 3, n)).astype(np.int8)

    # Slow population drift across the year: applicants get a little weaker
    # and a little more leveraged month over month, with a small per-month
    # shock so the drift is not a straight line. Kept small enough that the
    # calibrated cutoffs still bind where they did.
    # Centred on the middle of the year: month-over-month drift is real (PSI
    # against the first cohort grows through the year) while the book's
    # aggregate risk is unchanged, so approval rates and bad rates stay where
    # the strategy calibration and the docs put them.
    month_shock = rng.normal(0, 1.5, 12)
    months_ix = np.arange(12) - 5.5
    score_drift = (-1.15 * months_ix + month_shock).astype(np.float32)
    dti_drift = (0.0022 * months_ix).astype(np.float32)
    score = np.clip(score + score_drift[book_month], 520, 840).astype(np.float32)
    dti = np.clip(dti + dti_drift[book_month], 0.10, 0.88).astype(np.float32)

    # Latent PD from the scorecard features (same predictor the models estimate)
    logit_pd = _risk_logit(score, dti, num_loans, num_inquiries, tenure, age_band)
    pd_true = 1.0 / (1.0 + np.exp(-logit_pd))

    # Realised MOB12 bad flag
    bad = (rng.uniform(0, 1, n) < pd_true).astype(np.int8)

    # ── Delinquency timeline ─────────────────────────────────────────────
    # For every account, the worst delinquency stage reached inside MOB12:
    #   0 never late · 1 hit 30dpd then cured · 2 hit 60dpd then cured · 3 bad (90+)
    # and the month-on-book of the first 30dpd event. Bad accounts default at
    # a month drawn from a Beta hazard that shifts earlier for riskier
    # accounts; their first 30dpd sits two months before the default.
    z = np.clip((pd_true - pd_true.mean()) / (pd_true.std() + 1e-9), -2.5, 2.5)
    alpha = np.clip(2.2 - 0.45 * z, 1.1, 3.4)
    default_mob = np.where(
        bad == 1,
        1 + np.floor(rng.beta(alpha, 2.6, n) * 12).astype(np.int16),
        0,
    ).clip(0, 12).astype(np.int8)

    p_late = np.clip(0.03 + 0.30 * pd_true, 0.0, 0.5)
    late_once = (bad == 0) & (rng.uniform(0, 1, n) < p_late)
    reached_60 = late_once & (rng.uniform(0, 1, n) < 0.30)
    dpd_stage = np.where(bad == 1, 3, np.where(reached_60, 2, np.where(late_once, 1, 0))).astype(np.int8)
    first_dpd_mob = np.where(
        bad == 1,
        np.maximum(default_mob.astype(np.int16) - 2, 1),
        np.where(late_once, rng.integers(1, 13, n), 0),
    ).astype(np.int8)

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
        ("book_month", np.int8),
        ("default_mob", np.int8),
        ("dpd_stage", np.int8),
        ("first_dpd_mob", np.int8),
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
    result["book_month"] = book_month
    result["default_mob"] = default_mob
    result["dpd_stage"] = dpd_stage
    result["first_dpd_mob"] = first_dpd_mob
    return result


def _has_time_axis(df: np.ndarray) -> bool:
    names = df.dtype.names or ()
    return "book_month" in names and "default_mob" in names


def _psi(base: np.ndarray, comp: np.ndarray, n_bins: int = 10) -> float:
    """Population Stability Index between two samples of one variable."""
    if len(base) < 20 or len(comp) < 20:
        return 0.0
    edges = np.quantile(base, np.linspace(0, 1, n_bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    b = np.histogram(base, bins=edges)[0] / len(base)
    c = np.histogram(comp, bins=edges)[0] / len(comp)
    b = np.clip(b, 1e-4, None)
    c = np.clip(c, 1e-4, None)
    return float(np.sum((c - b) * np.log(c / b)))


# ---------------------------------------------------------------------------
# Strategy approval mask
# ---------------------------------------------------------------------------

# Per-strategy approval-rate calibration targets for the synthetic demo book.
# strategy's model-score cutoff is calibrated to hit this rate, so the cutoff
# is a real model threshold rather than a hardcoded number.
_PD_TARGET = settings.pd_target_approval_rates  # configurable via PD_TARGET_APPROVAL_RATES (JSON)
_PD_THRESHOLD_CACHE: dict[tuple, float] = {}


_OVERRIDABLE_POLICY = {
    "dti_limit", "mob_months", "mob_dpd_max", "score_cutoff",
    "limit_increase_min", "limit_increase_max", "target_approval_rate",
}


def _merged_policy(strategy_id: str, overrides: Optional[dict] = None) -> dict:
    """Built-in strategy definition with caller-supplied knobs applied.

    Only whitelisted keys may be overridden, so a parameter sweep (human or
    agent) can move a cutoff without being able to redefine the strategy.
    """
    s = dict(STRATEGIES[strategy_id])
    if overrides:
        unknown = set(overrides) - _OVERRIDABLE_POLICY
        if unknown:
            raise ValueError(f"non-overridable policy keys: {sorted(unknown)}")
        s.update(overrides)
    return s


def _ov_key(overrides: Optional[dict]) -> str:
    """Stable cache key for an override dict."""
    return json.dumps(overrides or {}, sort_keys=True)


def _eligible_mask(df: np.ndarray, strategy_id: str,
                   overrides: Optional[dict] = None) -> np.ndarray:
    """Hard policy gates (independent of the model score): DTI cap, zero
    delinquency over the MOB window, and v2.4-Beta's behaviour/thin-file gate
    that screens out ~40% of young applicants (its genuine DI source)."""
    s = _merged_policy(strategy_id, overrides)
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


def _pd_threshold(strategy_id: str, overrides: Optional[dict] = None) -> float:
    """Model-score (pd̂) cutoff calibrated on the reference population to hit the
    strategy's target approval rate. Cached per (strategy, overrides)."""
    key = (strategy_id, _ov_key(overrides))
    if key not in _PD_THRESHOLD_CACHE:
        s = _merged_policy(strategy_id, overrides)
        ref = generate_synthetic_data(n=50000, seed=42)
        elig = _eligible_mask(ref, strategy_id, overrides)
        pd_elig = np.sort(_model_score(ref, strategy_id)[elig])
        target = float(s.get("target_approval_rate",
                             _PD_TARGET.get(strategy_id, 0.4)))
        target_n = int(target * len(ref))
        if len(pd_elig) == 0:
            _PD_THRESHOLD_CACHE[key] = 1.0
        else:
            k = min(max(target_n, 0), len(pd_elig) - 1)
            _PD_THRESHOLD_CACHE[key] = float(pd_elig[k])
    return _PD_THRESHOLD_CACHE[key]


def _approve_mask(df: np.ndarray, strategy_id: str,
                  overrides: Optional[dict] = None) -> np.ndarray:
    """Approve customers the strategy's own model ranks as lowest-risk
    (pd̂ ≤ calibrated cutoff), subject to the hard policy gates. Because each
    strategy uses a different model, the approved sets genuinely disagree in
    both directions (swap-in AND swap-out), not just as nested supersets.
    """
    return (_eligible_mask(df, strategy_id, overrides)
            & (_model_score(df, strategy_id) <= _pd_threshold(strategy_id, overrides)))


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

    # PSI of the approved book's score distribution, month by month against
    # the first booking month. Measured from the data when it has a time
    # axis; only the legacy simulated series remains for books that do not.
    psi_trend, psi_simulated = _psi_trend(df, approved, strategy_id)

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

    # Rank ordering: does realised bad rate rise monotonically with the
    # model's risk estimate across the whole applicant population? A model can
    # post a fine AUC and still invert in a band — and a cutoff sits on a band.
    rank_ordering = _rank_ordering(df, strategy_id)

    return {
        "auc": round(auc, 4),
        "ks": round(float(ks_stat), 4),
        "lift_at_20": round(lift_at_20, 3),
        "brier_score": round(brier, 4),
        "roc_curve": roc_points,
        "psi_trend": psi_trend,
        "psi_simulated": psi_simulated,
        "calibration": calib_points,
        "rank_ordering": rank_ordering,
        "n_approved": int(approved.sum()),
    }


def _psi_trend(df: np.ndarray, approved: np.ndarray, strategy_id: str) -> tuple[list, bool]:
    if _has_time_axis(df):
        months = df["book_month"].astype(int)
        base = df["score"][approved & (months == 0)].astype(float)
        out = []
        for m in range(12):
            comp = df["score"][approved & (months == m)].astype(float)
            out.append({"month": f"M{m + 1}", "psi": round(_psi(base, comp), 4)})
        return out, False
    rng_psi = np.random.default_rng(int(hashlib.md5(strategy_id.encode()).hexdigest(), 16) % (2**32))
    psi_base = 0.04 if strategy_id == "v2.2" else (0.06 if strategy_id == "v2.3" else 0.09)
    return ([{"month": f"M{i + 1}", "psi": round(float(psi_base + rng_psi.normal(0, 0.008)), 4)}
             for i in range(6)], True)


def compute_csi_from_book(df: np.ndarray, features: Optional[list] = None) -> list[dict]:
    """Characteristic stability: first half of the booking year vs second half,
    per scorecard input. Measured on the applicant population."""
    if not _has_time_axis(df):
        return []
    features = features or ["score", "dti", "num_loans", "num_inquiries", "tenure"]
    months = df["book_month"].astype(int)
    early, late = months < 6, months >= 6
    out = []
    for f in features:
        if f not in (df.dtype.names or ()):
            continue
        v = _psi(df[f][early].astype(float), df[f][late].astype(float))
        out.append({"feature": f, "csi": round(v, 4), "stable": v < 0.10})
    return out


def _rank_ordering(df: np.ndarray, strategy_id: str, n_bins: int = 10) -> dict:
    """Bad rate by model-score decile (ascending risk) and a monotonicity flag."""
    pd_hat = _model_score(df, strategy_id).astype(float)
    bad = df["bad"].astype(float)
    if len(df) < n_bins * 20:
        return {"bins": [], "monotonic": None, "inversions": None}
    edges = np.quantile(pd_hat, np.linspace(0, 1, n_bins + 1))
    bins = []
    rates = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (pd_hat >= lo) & (pd_hat <= hi) if i == n_bins - 1 else (pd_hat >= lo) & (pd_hat < hi)
        if m.sum() == 0:
            continue
        rate = float(bad[m].mean())
        rates.append(rate)
        bins.append({"decile": i + 1, "n": int(m.sum()), "bad_rate": round(rate, 4),
                     "pd_hat_mean": round(float(pd_hat[m].mean()), 4)})
    inversions = sum(1 for a, b in zip(rates, rates[1:]) if b < a)
    return {"bins": bins, "monotonic": inversions == 0, "inversions": inversions}


# ---------------------------------------------------------------------------
# L2: Business value metrics
# ---------------------------------------------------------------------------

# Risk-based pricing margin per strategy (a business pricing assumption, not a
# risk metric): better-discriminating strategies price risk more sharply and
# capture more net interest margin on the incremental balance.
_PRICING_MARGIN = {"v2.2": 0.150, "v2.3": 0.182, "v2.4-Beta": 0.168, "v2.5-RC": 0.176}
_LGD = 0.55
_CAPITAL_RATIO = 0.72  # scales (margin - EL) into a realistic RAROC band


def _compute_l2(df: np.ndarray, strategy_id: str, approved: np.ndarray,
                overrides: Optional[dict] = None) -> dict:
    n_total = len(df)
    n_approved = int(approved.sum())
    approval_rate = round(n_approved / n_total, 4)

    sub = df[approved]
    bad_rate = round(float(sub["bad"].mean()), 4) if len(sub) > 0 else 0.0

    s = _merged_policy(strategy_id, overrides)
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

    rejection_reasons = compute_rejection_reasons(df, strategy_id, overrides)
    # Share of declines a concrete rule accounts for. It sat in L5 as a
    # fairness metric, which it is not: it is an explainability property of
    # the decline reasons, and it belongs beside them.
    reason_coverage = round(sum(r["pct"] for r in rejection_reasons if r["reason"] != "其他"), 4) \
        if rejection_reasons else 1.0

    return {
        "approval_rate": approval_rate,
        "n_approved": n_approved,
        # Absolute scale. Rates decide which strategy wins; these decide
        # whether the win is worth an approval cycle.
        "total_balance": round(incremental_balance * n_approved, 0),
        "total_revenue": round(revenue_per * n_approved, 0),
        "total_profit": round(profit_per * n_approved, 0),
        "reason_coverage": reason_coverage,
        "bad_rate": bad_rate,
        "avg_loan_amount": avg_loan,
        "revenue_per_approved": round(revenue_per, 2),
        "el_per_approved": round(el_per, 2),
        "avg_profit_per_approved": round(profit_per, 2),
        "raroc": raroc,
        "el_total": round(el_total, 0),
        "economic_capital": round(economic_capital, 0),
        "pareto_frontier": pareto,
        "rejection_reasons": rejection_reasons,
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
    n = len(sub)
    bad_rate = round(float(sub["bad"].mean()), 4) if n > 0 else 0.0

    if not _has_time_axis(df) or n == 0:
        return _l3_derived(bad_rate, strategy_id)

    stage = sub["dpd_stage"].astype(int)
    first = sub["first_dpd_mob"].astype(int)
    dmob = sub["default_mob"].astype(int)
    months = sub["book_month"].astype(int)

    # First-payment default: the first 30dpd event lands on the first payment.
    fpd_mask = first == 1
    fpd_rate = round(float(fpd_mask.mean()), 4)

    # Roll rates from the worst stage each account actually reached:
    #   M0→M1  share of the book that was ever 30dpd
    #   M1→M2  of those, share that went on to 60dpd
    #   M2→M3+ of those, share that went on to 90+ (= bad)
    ever30 = stage >= 1
    ever60 = stage >= 2
    roll_rates = {
        "m0_to_m1": round(float(ever30.mean()), 4),
        "m1_to_m2": round(float(ever60.sum() / max(ever30.sum(), 1)), 4),
        "m2_to_m3plus": round(float((stage == 3).sum() / max(ever60.sum(), 1)), 4),
    }

    # Vintage: cumulative share of the book that has defaulted by MOB m.
    vintage_curve = [
        {"month": m, "cum_bad_rate": round(float(((dmob >= 1) & (dmob <= m)).mean()), 4)}
        for m in range(1, 13)
    ]

    # FPD by booking month — a real trend, not a jittered constant.
    fpd_trend = []
    for m in range(12):
        cohort = months == m
        rate = float(fpd_mask[cohort].mean()) if cohort.sum() >= 50 else fpd_rate
        fpd_trend.append({"month": f"M{m + 1}", "fpd_rate": round(rate, 4), "n": int(cohort.sum())})

    return {
        "mob12_bad_rate": bad_rate,
        "fpd_rate": fpd_rate,
        "roll_rates": roll_rates,
        "vintage_curve": vintage_curve,
        "fpd_monthly_trend": fpd_trend,
        "derived": False,
        "observed_on": "book_month / dpd_stage / first_dpd_mob / default_mob",
    }


def _l3_derived(bad_rate: float, strategy_id: str) -> dict:
    """Legacy fallback for books without a delinquency timeline (uploaded
    datasets). Everything here is a function of the bad rate and is flagged."""
    fpd_rate = round(max(bad_rate * 0.32, 0.001), 4)
    m0m1 = round(min(0.020 + bad_rate * 1.1, 0.14), 4)
    roll_rates = {
        "m0_to_m1": m0m1,
        "m1_to_m2": round(0.52 + bad_rate * 3.5, 4),
        "m2_to_m3plus": round(0.60 + bad_rate * 3.0, 4),
    }
    vintage_curve = [{"month": m, "cum_bad_rate": round(float(bad_rate * (1 / (1 + np.exp(-0.7 * (m - 6))))), 4)}
                     for m in range(1, 13)]
    rng_fpd = np.random.default_rng(int(hashlib.md5((strategy_id + "_fpd").encode()).hexdigest(), 16) % (2**32))
    fpd_trend = [{"month": f"M{i + 1}", "fpd_rate": round(float(max(fpd_rate * (1 + rng_fpd.normal(0, 0.12)), 0.001)), 4)}
                 for i in range(6)]
    return {
        "mob12_bad_rate": bad_rate,
        "fpd_rate": fpd_rate,
        "roll_rates": roll_rates,
        "vintage_curve": vintage_curve,
        "fpd_monthly_trend": fpd_trend,
        "derived": True,
        "derived_from": "mob12_bad_rate",
    }


# ---------------------------------------------------------------------------
# L4: Swap-set analysis
# ---------------------------------------------------------------------------

def _compute_l4(
    df: np.ndarray,
    challenger_id: str,
    champion_id: str,
    challenger_overrides: Optional[dict] = None,
    champion_overrides: Optional[dict] = None,
) -> dict:
    """Compare challenger vs champion decision quadrants."""
    chall_mask = _approve_mask(df, challenger_id, challenger_overrides)
    champ_mask = _approve_mask(df, champion_id, champion_overrides)

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
        # Consistency alone says how often the two agree in a band; what a
        # policy owner needs is what the disagreements in that band cost.
        band_in = swap_in_mask & band_mask
        band_out = swap_out_mask & band_mask
        band_consistency.append({
            "score_band": label,
            "n": int(band_mask.sum()),
            "consistency_pct": round(float(agree / band_mask.sum()), 4),
            "swap_in_n": int(band_in.sum()),
            "swap_in_bad_rate": round(_br(band_in), 4) if band_in.sum() else None,
            "swap_out_n": int(band_out.sum()),
            "swap_out_bad_rate": round(_br(band_out), 4) if band_out.sum() else None,
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
        # Why did the champion decline the accounts the challenger admits?
        # Which challenger rule declines the accounts the champion admits?
        # This is the table that turns "v2.3 approves more at flat bad rate"
        # into an accountable statement about which rule bought what.
        "swap_in_attribution": _gate_attribution(df, swap_in_mask, champion_id, champion_overrides),
        "swap_out_attribution": _gate_attribution(df, swap_out_mask, challenger_id, challenger_overrides),
        "swap_in_raroc": _swap_raroc(_br(swap_in_mask), challenger_id),
        "swap_out_raroc": _swap_raroc(_br(swap_out_mask), champion_id),
        "rule_diff": _rule_diff(challenger_id, champion_id, challenger_overrides, champion_overrides),
    }


def _swap_raroc(bad_rate: float, pricing_strategy_id: str) -> float:
    """RAROC of a swap population at the admitting strategy's pricing. The
    marginal number a policy change is actually judged on."""
    margin = _PRICING_MARGIN.get(pricing_strategy_id, 0.165)
    return round((margin - bad_rate * _LGD) / _CAPITAL_RATIO, 4)


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

def _compute_l5(df: np.ndarray, strategy_id: str, approved: np.ndarray,
                overrides: Optional[dict] = None) -> dict:
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
        "feature_importance": compute_feature_importance(df, strategy_id, approved, overrides),
        "has_compliance_issue": has_compliance_issue,
        "compliance_threshold": 0.80,
    }


# ---------------------------------------------------------------------------
# Real attribution / decomposition computations
# ---------------------------------------------------------------------------

def compute_feature_importance(
    df: np.ndarray, strategy_id: str, approved: Optional[np.ndarray] = None,
    overrides: Optional[dict] = None,
) -> list[dict]:
    """Permutation feature importance of the scorecard inputs.

    For each feature, shuffle it on the approved book and measure the drop in
    the model's AUC; normalise the drops to sum to 1. Signed by risk direction.
    """
    if approved is None:
        approved = _approve_mask(df, strategy_id, overrides)
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


def _gate_attribution(df: np.ndarray, population: np.ndarray, strategy_id: str,
                      overrides: Optional[dict] = None) -> list[dict]:
    """Which of ``strategy_id``'s rules is the *first* to decline each account
    in ``population``. Priority-ordered, so every account lands in exactly one
    bucket. Returns per-rule count, share and realised bad rate.

    Used twice: for a strategy's own rejection reasons, and — pointed at the
    swap-set — to explain which rule *difference* moved which accounts."""
    s = _merged_policy(strategy_id, overrides)
    n_pop = int(population.sum())
    if n_pop == 0:
        return []
    bad = df["bad"].astype(float)
    remaining = population.copy()
    rows: list[dict] = []

    def _take(cond: np.ndarray, label: str, rule: str) -> None:
        nonlocal remaining
        hit = remaining & cond
        c = int(hit.sum())
        if c > 0:
            rows.append({"reason": label, "rule": rule, "n": c,
                         "pct": round(c / n_pop, 4),
                         "bad_rate": round(float(bad[hit].mean()), 4)})
        remaining = remaining & ~cond

    _take(df["dti"] > s["dti_limit"], "负债率过高", f"dti > {s['dti_limit']}")
    if s.get("mob_dpd_max") == 0:
        _take(df["months_clean"] < s["mob_months"], "近期逾期记录",
              f"months_clean < {s['mob_months']}")
    if strategy_id == "v2.4-Beta":
        _take(df["age_band"] == 0, "薄文件/行为不足", "thin-file gate (age 18-25)")
    thr = _pd_threshold(strategy_id, overrides)
    _take(_model_score(df, strategy_id) > thr, "风险评分不足", f"pd_hat > {thr:.4f}")

    rest = int(remaining.sum())
    if rest > 0:
        rows.append({"reason": "其他", "rule": "—", "n": rest,
                     "pct": round(rest / n_pop, 4),
                     "bad_rate": round(float(bad[remaining].mean()), 4)})
    rows.sort(key=lambda r: -r["n"])
    return rows


def compute_rejection_reasons(df: np.ndarray, strategy_id: str,
                              overrides: Optional[dict] = None) -> list[dict]:
    """Distribution of the *primary* reason each rejected applicant was declined,
    derived from the strategy's actual rules (priority-ordered attribution)."""
    rejected = ~_approve_mask(df, strategy_id, overrides)
    return [{"reason": r["reason"], "pct": r["pct"]}
            for r in _gate_attribution(df, rejected, strategy_id, overrides)]


def _rule_diff(challenger_id: str, champion_id: str,
               challenger_overrides: Optional[dict], champion_overrides: Optional[dict]) -> list[dict]:
    """The policy parameters that actually differ between two strategies."""
    a = _merged_policy(challenger_id, challenger_overrides)
    b = _merged_policy(champion_id, champion_overrides)
    keys = ["score_cutoff", "dti_limit", "mob_months", "mob_dpd_max",
            "limit_increase_min", "limit_increase_max", "anti_fraud"]
    out = []
    for k in keys:
        if a.get(k) != b.get(k):
            out.append({"param": k, "champion": b.get(k), "challenger": a.get(k)})
    return out


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
        out.append({"band": label, "raroc": round(raroc, 4)})
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_strategy(df: np.ndarray, strategy_id: str, champion_id: str = "v2.2",
                   overrides: Optional[dict] = None,
                   champion_overrides: Optional[dict] = None) -> dict:
    """
    Compute all L1-L5 metrics for a given strategy against the data.

    Returns a dict with keys: l1, l2, l3, l4, l5, strategy_info
    """
    if strategy_id not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_id}")

    approved = _approve_mask(df, strategy_id, overrides)

    l1 = _compute_l1(df, strategy_id, approved)
    l2 = _compute_l2(df, strategy_id, approved, overrides)
    l3 = _compute_l3(df, strategy_id, approved)
    l4 = _compute_l4(df, strategy_id, champion_id, overrides, champion_overrides)
    l5 = _compute_l5(df, strategy_id, approved, overrides)

    strategy_info = dict(STRATEGIES[strategy_id])
    if overrides:
        strategy_info["policy_overrides"] = dict(overrides)

    return {
        "strategy_info": strategy_info,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "l4": l4,
        "l5": l5,
    }
