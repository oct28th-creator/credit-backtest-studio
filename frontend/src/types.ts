export type Language = 'zh' | 'en';

export type StrategyRole = 'challenger' | 'champion' | 'beta';

export interface Strategy {
  id: string;
  nickname: string;
  name: string;
  role: StrategyRole;
  desc_zh: string;
  desc_en: string;
  online_since?: string;
  score_cutoff?: number | null;
  dti_limit: number;
  mob_months: number;
  limit_increase_min: number;
  limit_increase_max: number;
  anti_fraud: string;
  rules: StrategyRules;
}

export interface StrategyRules {
  anti_fraud_rules: Array<{ rule: string; desc_zh: string; desc_en: string }>;
  if_else: Array<{ condition: string; action_zh: string; action_en: string }>;
  scorecard_features: Array<{ feature: string; weight: number; direction: 'positive' | 'negative' }>;
  decision_table: Array<{ dti_band: string; score_band: string; action_zh: string; action_en: string; rate: string }>;
  bifurcation: Array<{ branch_zh: string; branch_en: string; pct: number; bad_rate: number | null }>;
}

export interface Sample {
  id: string;
  name_zh: string;
  name_en: string;
  vintage: string;
  product_mix_zh: string;
  product_mix_en: string;
  channels_zh: string;
  channels_en: string;
  n_rows: number;
  lookback_months: number;
  perf_window_months: number;
  desc_zh: string;
  desc_en: string;
}

export interface ExperimentConfig {
  challenger: string;
  champion: string;
  beta: string | null;
  sample_id: string;
  lookback_months: number;
  perf_window_months: number;
  ri_mode: string;
  slice_dim: string | null;
  slice_value: string | null;
  language: Language;
}

export interface KpiL1 { version: string; ks: number; auc: number; lift20: number; brier: number; }
export interface KpiL2 { version: string; approval_rate: number; avg_profit: number; raroc: number; el: number; }
export interface KpiL3 { version: string; m12_bad: number; m1_m2_roll: number; fpd: number; }

export interface SwapMatrix {
  double_approve: { count: number; bad_rate: number };
  swap_in: { count: number; bad_rate: number };
  swap_out: { count: number; bad_rate: number };
  double_reject: { count: number; bad_rate: null };
  consistency: number;
  consistency_count: number;
  consistency_total: number;
  p_value: number;
  base_bad_rate: number;
  swap_out_lift: number;
  consistency_by_band: Array<{ band: string; consistency: number }>;
}

export interface L5Kpis { di_female_male: number; di_delta_vs_champ: number; tpr_gap: number; reason_coverage: number; }

export interface RunResult {
  run_id: string;
  champion: string;
  challenger: string;
  beta: string | null;
  sample_size: number;
  duration_s: number;
  snapshot_sha: string;
  config: ExperimentConfig;
  layers: {
    l1: {
      kpis: KpiL1[];
      psi_monthly: Array<{ month: string; psi: number; tone: string }>;
      roc: Record<string, Array<{ fpr: number; tpr: number }>>;
      calibration: Record<string, Array<{ pd_pred: number; actual: number }>>;
      csi: Array<{ feature: string; csi: number }>;
    };
    l2: {
      kpis: KpiL2[];
      frontier: Array<Record<string, number>>;
      rejection_reasons: Record<string, Array<{ reason: string; pct: number }>>;
      raroc_bands: Record<string, Array<{ band: string; raroc: number }>>;
    };
    l3: {
      kpis: KpiL3[];
      vintage: Array<Record<string, number>>;
      fpd_trend: Array<Record<string, number | string>>;
      roll_rates: Record<string, { m0_m1: number; m1_m2: number; m2_m3plus: number }>;
    };
    l4: {
      matrices: Record<string, SwapMatrix>;
    };
    l5: {
      kpis: L5Kpis;
      di_by_group: Record<string, { female_male: number; outsider_local: number; young_core: number }>;
      shap: Record<string, Array<{ feature: string; shap: number }>>;
    };
  };
}

export interface AIAnalysis {
  findings: string[];
  warnings: string[];
  recommendations: string[];
}

export interface ChatMessage {
  role: 'user' | 'ai';
  content: string;
}

export type Screen = 'config' | 'execution' | 'results' | 'history';
export type ResultsTab = 'strategy' | 'metrics';
export type MetricsLayer = 'l1' | 'l2' | 'l3' | 'l4' | 'l5';
