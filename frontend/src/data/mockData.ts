import type { Strategy, Sample, RunResult, ExperimentConfig } from '../types';

export const STRAT_COLORS = {
  'v2.2': '#7a6a55',
  'v2.3': '#1f5d6d',
  'v2.4-Beta': '#bf6b3f',
  'v2.5-RC': '#6c5aa6',
} as const;

export const MOCK_STRATEGIES: Strategy[] = [
  {
    id: 'v2.3',
    nickname: 'v2.3',
    name: '信贷策略 v2.3',
    role: 'challenger',
    desc_zh: '当前挑战者策略，采用升级评分卡，重点优化中高分段',
    desc_en: 'Current challenger strategy with upgraded scorecard, focusing on mid-high score bands',
    online_since: '2024-06-01',
    score_cutoff: 620,
    dti_limit: 0.45,
    mob_months: 12,
    limit_increase_min: 2000,
    limit_increase_max: 50000,
    anti_fraud: 'AF-v3',
    rules: {
      anti_fraud_rules: [
        { rule: 'AF-001', desc_zh: '设备指纹黑名单', desc_en: 'Device fingerprint blacklist' },
        { rule: 'AF-002', desc_zh: '社交网络欺诈图谱', desc_en: 'Social network fraud graph' },
        { rule: 'AF-003', desc_zh: '地址核验', desc_en: 'Address verification' },
        { rule: 'AF-004', desc_zh: '申请速率限制', desc_en: 'Application velocity limit' },
      ],
      if_else: [
        { condition: 'DTI > 0.45', action_zh: '直接拒绝', action_en: 'Hard reject' },
        { condition: 'score < 580', action_zh: '直接拒绝', action_en: 'Hard reject' },
        { condition: 'MOB < 3', action_zh: '保守策略', action_en: 'Conservative policy' },
        { condition: 'score >= 720', action_zh: '高额提升', action_en: 'High limit increase' },
      ],
      scorecard_features: [
        { feature: '历史还款准时率', weight: 0.32, direction: 'positive' },
        { feature: '信用卡使用率', weight: 0.18, direction: 'negative' },
        { feature: '账龄', weight: 0.15, direction: 'positive' },
        { feature: '查询次数(6月)', weight: 0.14, direction: 'negative' },
        { feature: '收入稳定性', weight: 0.12, direction: 'positive' },
        { feature: 'DTI', weight: 0.09, direction: 'negative' },
      ],
      decision_table: [
        { dti_band: '0-0.20', score_band: '680+', action_zh: '高额提升', action_en: 'High increase', rate: '14.9%' },
        { dti_band: '0-0.20', score_band: '620-680', action_zh: '标准提升', action_en: 'Standard increase', rate: '16.9%' },
        { dti_band: '0.20-0.35', score_band: '680+', action_zh: '标准提升', action_en: 'Standard increase', rate: '16.9%' },
        { dti_band: '0.20-0.35', score_band: '620-680', action_zh: '小额提升', action_en: 'Small increase', rate: '18.9%' },
        { dti_band: '0.35-0.45', score_band: '680+', action_zh: '小额提升', action_en: 'Small increase', rate: '18.9%' },
        { dti_band: '0.35-0.45', score_band: '620-680', action_zh: '拒绝', action_en: 'Reject', rate: '-' },
      ],
      bifurcation: [
        { branch_zh: '高质量客群', branch_en: 'High Quality', pct: 0.38, bad_rate: 0.012 },
        { branch_zh: '标准客群', branch_en: 'Standard', pct: 0.44, bad_rate: 0.028 },
        { branch_zh: '边缘客群', branch_en: 'Marginal', pct: 0.18, bad_rate: 0.071 },
      ],
    },
  },
  {
    id: 'v2.2',
    nickname: 'v2.2',
    name: '信贷策略 v2.2',
    role: 'champion',
    desc_zh: '当前基准策略，已稳定运行18个月，风险参数保守',
    desc_en: 'Current champion strategy, stable for 18 months with conservative risk parameters',
    online_since: '2023-01-15',
    score_cutoff: 640,
    dti_limit: 0.40,
    mob_months: 12,
    limit_increase_min: 1000,
    limit_increase_max: 30000,
    anti_fraud: 'AF-v2',
    rules: {
      anti_fraud_rules: [
        { rule: 'AF-001', desc_zh: '设备指纹黑名单', desc_en: 'Device fingerprint blacklist' },
        { rule: 'AF-002', desc_zh: '社交网络欺诈图谱', desc_en: 'Social network fraud graph' },
        { rule: 'AF-003', desc_zh: '地址核验', desc_en: 'Address verification' },
      ],
      if_else: [
        { condition: 'DTI > 0.40', action_zh: '直接拒绝', action_en: 'Hard reject' },
        { condition: 'score < 600', action_zh: '直接拒绝', action_en: 'Hard reject' },
        { condition: 'score >= 700', action_zh: '高额提升', action_en: 'High limit increase' },
      ],
      scorecard_features: [
        { feature: '历史还款准时率', weight: 0.35, direction: 'positive' },
        { feature: '信用卡使用率', weight: 0.20, direction: 'negative' },
        { feature: '账龄', weight: 0.18, direction: 'positive' },
        { feature: '查询次数(6月)', weight: 0.15, direction: 'negative' },
        { feature: '收入稳定性', weight: 0.12, direction: 'positive' },
      ],
      decision_table: [
        { dti_band: '0-0.20', score_band: '700+', action_zh: '高额提升', action_en: 'High increase', rate: '15.9%' },
        { dti_band: '0-0.20', score_band: '640-700', action_zh: '标准提升', action_en: 'Standard increase', rate: '17.9%' },
        { dti_band: '0.20-0.30', score_band: '700+', action_zh: '标准提升', action_en: 'Standard increase', rate: '17.9%' },
        { dti_band: '0.20-0.30', score_band: '640-700', action_zh: '小额提升', action_en: 'Small increase', rate: '19.9%' },
        { dti_band: '0.30-0.40', score_band: '700+', action_zh: '小额提升', action_en: 'Small increase', rate: '19.9%' },
        { dti_band: '0.30-0.40', score_band: '640-700', action_zh: '拒绝', action_en: 'Reject', rate: '-' },
      ],
      bifurcation: [
        { branch_zh: '高质量客群', branch_en: 'High Quality', pct: 0.28, bad_rate: 0.008 },
        { branch_zh: '标准客群', branch_en: 'Standard', pct: 0.52, bad_rate: 0.022 },
        { branch_zh: '边缘客群', branch_en: 'Marginal', pct: 0.20, bad_rate: 0.065 },
      ],
    },
  },
  {
    id: 'v2.4-Beta',
    nickname: 'v2.4-Beta',
    name: '信贷策略 v2.4-Beta',
    role: 'beta',
    desc_zh: '激进增长版本，显著放宽审批标准，关注规模扩张',
    desc_en: 'Aggressive growth version, significantly relaxed approval criteria, growth-focused',
    score_cutoff: 600,
    dti_limit: 0.50,
    mob_months: 12,
    limit_increase_min: 3000,
    limit_increase_max: 80000,
    anti_fraud: 'AF-v3',
    rules: {
      anti_fraud_rules: [
        { rule: 'AF-001', desc_zh: '设备指纹黑名单', desc_en: 'Device fingerprint blacklist' },
        { rule: 'AF-002', desc_zh: '社交网络欺诈图谱', desc_en: 'Social network fraud graph' },
        { rule: 'AF-003', desc_zh: '地址核验', desc_en: 'Address verification' },
        { rule: 'AF-004', desc_zh: '申请速率限制', desc_en: 'Application velocity limit' },
        { rule: 'AF-005', desc_zh: 'ML 实时欺诈评分', desc_en: 'ML real-time fraud score' },
      ],
      if_else: [
        { condition: 'DTI > 0.50', action_zh: '直接拒绝', action_en: 'Hard reject' },
        { condition: 'score < 560', action_zh: '直接拒绝', action_en: 'Hard reject' },
        { condition: 'MOB < 2', action_zh: '小额提升', action_en: 'Small increase' },
        { condition: 'score >= 680', action_zh: '高额提升', action_en: 'High limit increase' },
      ],
      scorecard_features: [
        { feature: '历史还款准时率', weight: 0.28, direction: 'positive' },
        { feature: '信用卡使用率', weight: 0.16, direction: 'negative' },
        { feature: '账龄', weight: 0.12, direction: 'positive' },
        { feature: '查询次数(6月)', weight: 0.12, direction: 'negative' },
        { feature: '收入稳定性', weight: 0.10, direction: 'positive' },
        { feature: 'DTI', weight: 0.08, direction: 'negative' },
        { feature: '行为特征 ML', weight: 0.14, direction: 'positive' },
      ],
      decision_table: [
        { dti_band: '0-0.25', score_band: '660+', action_zh: '高额提升', action_en: 'High increase', rate: '13.9%' },
        { dti_band: '0-0.25', score_band: '600-660', action_zh: '标准提升', action_en: 'Standard increase', rate: '15.9%' },
        { dti_band: '0.25-0.40', score_band: '660+', action_zh: '标准提升', action_en: 'Standard increase', rate: '15.9%' },
        { dti_band: '0.25-0.40', score_band: '600-660', action_zh: '小额提升', action_en: 'Small increase', rate: '17.9%' },
        { dti_band: '0.40-0.50', score_band: '660+', action_zh: '小额提升', action_en: 'Small increase', rate: '17.9%' },
        { dti_band: '0.40-0.50', score_band: '600-660', action_zh: '拒绝', action_en: 'Reject', rate: '-' },
      ],
      bifurcation: [
        { branch_zh: '高质量客群', branch_en: 'High Quality', pct: 0.45, bad_rate: 0.018 },
        { branch_zh: '标准客群', branch_en: 'Standard', pct: 0.38, bad_rate: 0.038 },
        { branch_zh: '边缘客群', branch_en: 'Marginal', pct: 0.17, bad_rate: 0.095 },
      ],
    },
  },
  {
    id: 'v2.5-RC',
    nickname: 'v2.5-RC',
    name: '信贷策略 v2.5-RC',
    role: 'beta',
    desc_zh: '发布候选版本，融合 AI 决策辅助，平衡增长与风险',
    desc_en: 'Release candidate with AI decision assist, balanced growth and risk',
    score_cutoff: 610,
    dti_limit: 0.45,
    mob_months: 12,
    limit_increase_min: 2000,
    limit_increase_max: 60000,
    anti_fraud: 'AF-v4',
    rules: {
      anti_fraud_rules: [
        { rule: 'AF-001', desc_zh: '设备指纹黑名单', desc_en: 'Device fingerprint blacklist' },
        { rule: 'AF-002', desc_zh: '社交网络欺诈图谱', desc_en: 'Social network fraud graph' },
        { rule: 'AF-003', desc_zh: '地址核验', desc_en: 'Address verification' },
        { rule: 'AF-004', desc_zh: '申请速率限制', desc_en: 'Application velocity limit' },
        { rule: 'AF-005', desc_zh: 'ML 实时欺诈评分', desc_en: 'ML real-time fraud score' },
        { rule: 'AF-006', desc_zh: 'AI 行为异常检测', desc_en: 'AI behavior anomaly detection' },
      ],
      if_else: [
        { condition: 'DTI > 0.45', action_zh: '直接拒绝', action_en: 'Hard reject' },
        { condition: 'score < 570', action_zh: '直接拒绝', action_en: 'Hard reject' },
        { condition: 'AI_risk > 0.85', action_zh: '人工审核', action_en: 'Manual review' },
        { condition: 'score >= 700', action_zh: '高额提升', action_en: 'High limit increase' },
      ],
      scorecard_features: [
        { feature: '历史还款准时率', weight: 0.30, direction: 'positive' },
        { feature: '信用卡使用率', weight: 0.17, direction: 'negative' },
        { feature: '账龄', weight: 0.13, direction: 'positive' },
        { feature: '查询次数(6月)', weight: 0.13, direction: 'negative' },
        { feature: '收入稳定性', weight: 0.11, direction: 'positive' },
        { feature: 'DTI', weight: 0.08, direction: 'negative' },
        { feature: 'AI 综合评分', weight: 0.08, direction: 'positive' },
      ],
      decision_table: [
        { dti_band: '0-0.20', score_band: '700+', action_zh: '高额提升', action_en: 'High increase', rate: '14.4%' },
        { dti_band: '0-0.20', score_band: '610-700', action_zh: '标准提升', action_en: 'Standard increase', rate: '16.4%' },
        { dti_band: '0.20-0.35', score_band: '700+', action_zh: '标准提升', action_en: 'Standard increase', rate: '16.4%' },
        { dti_band: '0.20-0.35', score_band: '610-700', action_zh: '小额提升', action_en: 'Small increase', rate: '18.4%' },
        { dti_band: '0.35-0.45', score_band: '700+', action_zh: '小额提升', action_en: 'Small increase', rate: '18.4%' },
        { dti_band: '0.35-0.45', score_band: '610-700', action_zh: '拒绝', action_en: 'Reject', rate: '-' },
      ],
      bifurcation: [
        { branch_zh: '高质量客群', branch_en: 'High Quality', pct: 0.42, bad_rate: 0.014 },
        { branch_zh: '标准客群', branch_en: 'Standard', pct: 0.41, bad_rate: 0.030 },
        { branch_zh: '边缘客群', branch_en: 'Marginal', pct: 0.17, bad_rate: 0.078 },
      ],
    },
  },
];

export const MOCK_SAMPLES: Sample[] = [
  {
    id: 'bf2023',
    name_zh: '黑五2023样本',
    name_en: 'Black Friday 2023',
    vintage: '2023-11',
    product_mix_zh: '信用卡75%、消费贷25%',
    product_mix_en: 'Credit Card 75%, Consumer Loan 25%',
    channels_zh: '线上80%、线下20%',
    channels_en: 'Online 80%, Offline 20%',
    n_rows: 142000,
    lookback_months: 12,
    perf_window_months: 12,
    desc_zh: '2023年黑色星期五大促期间申请样本，覆盖双十一前后各6周',
    desc_en: '2023 Black Friday promotional period applications, covering 6 weeks before and after Double 11',
  },
  {
    id: 'bf2022',
    name_zh: '黑五2022样本',
    name_en: 'Black Friday 2022',
    vintage: '2022-11',
    product_mix_zh: '信用卡80%、消费贷20%',
    product_mix_en: 'Credit Card 80%, Consumer Loan 20%',
    channels_zh: '线上70%、线下30%',
    channels_en: 'Online 70%, Offline 30%',
    n_rows: 118000,
    lookback_months: 12,
    perf_window_months: 12,
    desc_zh: '2022年黑色星期五大促申请样本',
    desc_en: '2022 Black Friday promotional period applications',
  },
];

const BASE_CONFIG: ExperimentConfig = {
  challenger: 'v2.3',
  champion: 'v2.2',
  beta: 'v2.4-Beta',
  sample_id: 'bf2023',
  lookback_months: 12,
  perf_window_months: 12,
  ri_mode: 'standard',
  slice_dim: null,
  slice_value: null,
  language: 'zh',
};

export const MOCK_RUN_RESULT: RunResult = {
  run_id: 'run-20241115-001',
  champion: 'v2.2',
  challenger: 'v2.3',
  beta: 'v2.4-Beta',
  sample_size: 142000,
  duration_s: 12.4,
  snapshot_sha: 'a3f8c21d',
  config: BASE_CONFIG,
  layers: {
    l1: {
      kpis: [
        { version: 'v2.3', ks: 0.48, auc: 0.83, lift20: 3.2, brier: 0.118 },
        { version: 'v2.2', ks: 0.42, auc: 0.78, lift20: 2.8, brier: 0.142 },
        { version: 'v2.4-Beta', ks: 0.43, auc: 0.79, lift20: 2.9, brier: 0.138 },
      ],
      psi_monthly: [
        { month: '2024-06', psi: 0.04, tone: 'green' },
        { month: '2024-07', psi: 0.06, tone: 'green' },
        { month: '2024-08', psi: 0.09, tone: 'green' },
        { month: '2024-09', psi: 0.12, tone: 'amber' },
        { month: '2024-10', psi: 0.08, tone: 'green' },
        { month: '2024-11', psi: 0.07, tone: 'green' },
      ],
      roc: {
        'v2.3': [
          { fpr: 0, tpr: 0 }, { fpr: 0.05, tpr: 0.22 }, { fpr: 0.10, tpr: 0.38 },
          { fpr: 0.20, tpr: 0.58 }, { fpr: 0.30, tpr: 0.72 }, { fpr: 0.40, tpr: 0.82 },
          { fpr: 0.50, tpr: 0.89 }, { fpr: 0.60, tpr: 0.93 }, { fpr: 0.80, tpr: 0.97 }, { fpr: 1, tpr: 1 },
        ],
        'v2.2': [
          { fpr: 0, tpr: 0 }, { fpr: 0.05, tpr: 0.18 }, { fpr: 0.10, tpr: 0.32 },
          { fpr: 0.20, tpr: 0.51 }, { fpr: 0.30, tpr: 0.66 }, { fpr: 0.40, tpr: 0.76 },
          { fpr: 0.50, tpr: 0.84 }, { fpr: 0.60, tpr: 0.90 }, { fpr: 0.80, tpr: 0.95 }, { fpr: 1, tpr: 1 },
        ],
        'v2.4-Beta': [
          { fpr: 0, tpr: 0 }, { fpr: 0.05, tpr: 0.19 }, { fpr: 0.10, tpr: 0.33 },
          { fpr: 0.20, tpr: 0.52 }, { fpr: 0.30, tpr: 0.67 }, { fpr: 0.40, tpr: 0.77 },
          { fpr: 0.50, tpr: 0.85 }, { fpr: 0.60, tpr: 0.91 }, { fpr: 0.80, tpr: 0.96 }, { fpr: 1, tpr: 1 },
        ],
      },
      calibration: {
        'v2.3': [
          { pd_pred: 0.01, actual: 0.012 }, { pd_pred: 0.02, actual: 0.021 },
          { pd_pred: 0.05, actual: 0.048 }, { pd_pred: 0.10, actual: 0.097 },
          { pd_pred: 0.20, actual: 0.196 }, { pd_pred: 0.30, actual: 0.302 },
        ],
        'v2.2': [
          { pd_pred: 0.01, actual: 0.014 }, { pd_pred: 0.02, actual: 0.025 },
          { pd_pred: 0.05, actual: 0.055 }, { pd_pred: 0.10, actual: 0.108 },
          { pd_pred: 0.20, actual: 0.212 }, { pd_pred: 0.30, actual: 0.318 },
        ],
        'v2.4-Beta': [
          { pd_pred: 0.01, actual: 0.013 }, { pd_pred: 0.02, actual: 0.022 },
          { pd_pred: 0.05, actual: 0.051 }, { pd_pred: 0.10, actual: 0.102 },
          { pd_pred: 0.20, actual: 0.205 }, { pd_pred: 0.30, actual: 0.308 },
        ],
      },
      csi: [
        { feature: '历史还款准时率', csi: 0.03 },
        { feature: '信用卡使用率', csi: 0.07 },
        { feature: '账龄', csi: 0.02 },
        { feature: '查询次数(6月)', csi: 0.11 },
        { feature: '收入稳定性', csi: 0.04 },
        { feature: 'DTI', csi: 0.06 },
      ],
    },
    l2: {
      kpis: [
        { version: 'v2.3', approval_rate: 0.38, avg_profit: 1840, raroc: 0.22, el: 0.028 },
        { version: 'v2.2', approval_rate: 0.28, avg_profit: 1620, raroc: 0.18, el: 0.021 },
        { version: 'v2.4-Beta', approval_rate: 0.45, avg_profit: 1520, raroc: 0.16, el: 0.038 },
      ],
      frontier: [
        { approval_rate: 0.20, avg_profit: 1950 },
        { approval_rate: 0.28, avg_profit: 1620 },
        { approval_rate: 0.35, avg_profit: 1880 },
        { approval_rate: 0.38, avg_profit: 1840 },
        { approval_rate: 0.45, avg_profit: 1520 },
        { approval_rate: 0.52, avg_profit: 1280 },
        { approval_rate: 0.60, avg_profit: 980 },
      ],
      rejection_reasons: {
        'v2.3': [
          { reason: 'DTI超限', pct: 0.32 },
          { reason: '评分不足', pct: 0.28 },
          { reason: 'MOB不足', pct: 0.21 },
          { reason: '反欺诈', pct: 0.12 },
          { reason: '其他', pct: 0.07 },
        ],
        'v2.2': [
          { reason: '评分不足', pct: 0.38 },
          { reason: 'DTI超限', pct: 0.28 },
          { reason: 'MOB不足', pct: 0.18 },
          { reason: '反欺诈', pct: 0.10 },
          { reason: '其他', pct: 0.06 },
        ],
        'v2.4-Beta': [
          { reason: 'DTI超限', pct: 0.38 },
          { reason: '评分不足', pct: 0.22 },
          { reason: '反欺诈', pct: 0.20 },
          { reason: 'MOB不足', pct: 0.12 },
          { reason: '其他', pct: 0.08 },
        ],
      },
      raroc_bands: {
        'v2.3': [
          { band: '580-620', raroc: 0.08 },
          { band: '620-660', raroc: 0.15 },
          { band: '660-700', raroc: 0.22 },
          { band: '700-740', raroc: 0.31 },
          { band: '740+', raroc: 0.40 },
        ],
        'v2.2': [
          { band: '580-620', raroc: 0.05 },
          { band: '620-660', raroc: 0.11 },
          { band: '660-700', raroc: 0.18 },
          { band: '700-740', raroc: 0.27 },
          { band: '740+', raroc: 0.36 },
        ],
        'v2.4-Beta': [
          { band: '580-620', raroc: 0.06 },
          { band: '620-660', raroc: 0.12 },
          { band: '660-700', raroc: 0.19 },
          { band: '700-740', raroc: 0.28 },
          { band: '740+', raroc: 0.37 },
        ],
      },
    },
    l3: {
      kpis: [
        { version: 'v2.3', m12_bad: 0.024, m1_m2_roll: 0.18, fpd: 0.032 },
        { version: 'v2.2', m12_bad: 0.018, m1_m2_roll: 0.15, fpd: 0.025 },
        { version: 'v2.4-Beta', m12_bad: 0.032, m1_m2_roll: 0.22, fpd: 0.041 },
      ],
      vintage: [
        { mob: 1, 'v2.3': 0.005, 'v2.2': 0.004, 'v2.4-Beta': 0.007 },
        { mob: 2, 'v2.3': 0.009, 'v2.2': 0.007, 'v2.4-Beta': 0.012 },
        { mob: 3, 'v2.3': 0.013, 'v2.2': 0.010, 'v2.4-Beta': 0.018 },
        { mob: 6, 'v2.3': 0.018, 'v2.2': 0.013, 'v2.4-Beta': 0.025 },
        { mob: 9, 'v2.3': 0.021, 'v2.2': 0.016, 'v2.4-Beta': 0.029 },
        { mob: 12, 'v2.3': 0.024, 'v2.2': 0.018, 'v2.4-Beta': 0.032 },
      ],
      fpd_trend: [
        { month: '2024-06', 'v2.3': 0.029, 'v2.2': 0.023, 'v2.4-Beta': 0.038 },
        { month: '2024-07', 'v2.3': 0.031, 'v2.2': 0.024, 'v2.4-Beta': 0.040 },
        { month: '2024-08', 'v2.3': 0.030, 'v2.2': 0.025, 'v2.4-Beta': 0.039 },
        { month: '2024-09', 'v2.3': 0.033, 'v2.2': 0.026, 'v2.4-Beta': 0.042 },
        { month: '2024-10', 'v2.3': 0.032, 'v2.2': 0.025, 'v2.4-Beta': 0.041 },
        { month: '2024-11', 'v2.3': 0.032, 'v2.2': 0.025, 'v2.4-Beta': 0.041 },
      ],
      roll_rates: {
        'v2.3': { m0_m1: 0.042, m1_m2: 0.18, m2_m3plus: 0.52 },
        'v2.2': { m0_m1: 0.033, m1_m2: 0.15, m2_m3plus: 0.48 },
        'v2.4-Beta': { m0_m1: 0.055, m1_m2: 0.22, m2_m3plus: 0.58 },
      },
    },
    l4: {
      matrices: {
        'v2.3_vs_v2.2': {
          double_approve: { count: 28400, bad_rate: 0.019 },
          swap_in: { count: 3240, bad_rate: 0.048 },
          swap_out: { count: 2610, bad_rate: 0.009 },
          double_reject: { count: 107750, bad_rate: null },
          consistency: 0.965,
          consistency_count: 136150,
          consistency_total: 142000,
          p_value: 0.012,
          base_bad_rate: 0.021,
          swap_out_lift: 0.57,
          consistency_by_band: [
            { band: '580-620', consistency: 0.921 },
            { band: '620-660', consistency: 0.948 },
            { band: '660-700', consistency: 0.972 },
            { band: '700-740', consistency: 0.988 },
            { band: '740+', consistency: 0.995 },
          ],
        },
        'v2.4-Beta_vs_v2.2': {
          double_approve: { count: 31200, bad_rate: 0.022 },
          swap_in: { count: 12800, bad_rate: 0.065 },
          swap_out: { count: 2800, bad_rate: 0.008 },
          double_reject: { count: 95200, bad_rate: null },
          consistency: 0.891,
          consistency_count: 126400,
          consistency_total: 142000,
          p_value: 0.001,
          base_bad_rate: 0.021,
          swap_out_lift: 0.62,
          consistency_by_band: [
            { band: '580-620', consistency: 0.782 },
            { band: '620-660', consistency: 0.851 },
            { band: '660-700', consistency: 0.912 },
            { band: '700-740', consistency: 0.962 },
            { band: '740+', consistency: 0.981 },
          ],
        },
      },
    },
    l5: {
      kpis: {
        di_female_male: 0.86,
        di_delta_vs_champ: 0.00,
        tpr_gap: 0.032,
        reason_coverage: 0.94,
      },
      di_by_group: {
        'v2.3': { female_male: 0.86, outsider_local: 0.88, young_core: 0.86 },
        'v2.2': { female_male: 0.94, outsider_local: 0.92, young_core: 0.94 },
        'v2.4-Beta': { female_male: 0.82, outsider_local: 0.79, young_core: 0.77 },
      },
      shap: {
        'v2.3': [
          { feature: '历史还款准时率', shap: 0.142 },
          { feature: '信用卡使用率', shap: -0.098 },
          { feature: '查询次数(6月)', shap: -0.074 },
          { feature: '账龄', shap: 0.068 },
          { feature: '收入稳定性', shap: 0.055 },
          { feature: 'DTI', shap: -0.041 },
        ],
        'v2.2': [
          { feature: '历史还款准时率', shap: 0.158 },
          { feature: '信用卡使用率', shap: -0.112 },
          { feature: '账龄', shap: 0.081 },
          { feature: '查询次数(6月)', shap: -0.069 },
          { feature: '收入稳定性', shap: 0.062 },
          { feature: 'DTI', shap: -0.038 },
        ],
        'v2.4-Beta': [
          { feature: '行为特征 ML', shap: 0.135 },
          { feature: '历史还款准时率', shap: 0.121 },
          { feature: '信用卡使用率', shap: -0.088 },
          { feature: '查询次数(6月)', shap: -0.079 },
          { feature: '账龄', shap: 0.058 },
          { feature: 'DTI', shap: -0.052 },
        ],
      },
    },
  },
};

export function applyMockSlice(base: RunResult, config: { slice_dim: string | null; slice_value: string | null }): RunResult {
  if (!config.slice_dim || !config.slice_value) return base;

  // Deterministic adjustment factor based on slice selection
  const sliceKey = `${config.slice_dim}_${config.slice_value}`;
  const seedMap: Record<string, number> = {
    'channel_online': 1.05,
    'channel_offline': 0.88,
    'channel_app': 1.08,
    'vintage_2023-11': 1.02,
    'vintage_2023-10': 0.96,
    'vintage_2023-12': 1.01,
    'product_credit_card': 1.03,
    'product_consumer_loan': 0.92,
    'age_band_18-25': 0.85,
    'age_band_26-35': 1.04,
    'age_band_36-45': 1.07,
    'age_band_46+': 0.98,
  };
  const factor = seedMap[sliceKey] ?? 1.0;

  const adjustKpiL1 = (k: typeof base.layers.l1.kpis[0]) => ({
    ...k,
    ks: Math.min(0.99, k.ks * factor),
    auc: Math.min(0.99, k.auc * (1 + (factor - 1) * 0.5)),
    lift20: k.lift20 * factor,
    brier: k.brier / factor,
  });

  const adjustKpiL2 = (k: typeof base.layers.l2.kpis[0]) => ({
    ...k,
    approval_rate: Math.min(0.99, k.approval_rate * factor),
    avg_profit: k.avg_profit * factor,
    raroc: Math.min(0.99, k.raroc * factor),
    el: k.el * (2 - factor),
  });

  const adjustKpiL3 = (k: typeof base.layers.l3.kpis[0]) => ({
    ...k,
    m12_bad: k.m12_bad * (2 - factor),
    m1_m2_roll: k.m1_m2_roll * (2 - factor),
    fpd: k.fpd * (2 - factor),
  });

  return {
    ...base,
    config: { ...base.config, ...config },
    layers: {
      ...base.layers,
      l1: { ...base.layers.l1, kpis: base.layers.l1.kpis.map(adjustKpiL1) },
      l2: { ...base.layers.l2, kpis: base.layers.l2.kpis.map(adjustKpiL2) },
      l3: { ...base.layers.l3, kpis: base.layers.l3.kpis.map(adjustKpiL3) },
    },
  };
}
