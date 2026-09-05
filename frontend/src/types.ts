export type Language = 'zh' | 'en';

export type StrategyRole = 'challenger' | 'champion' | 'beta';

export interface Strategy {
  id: string;
  nickname: string;
  nickname_en?: string;
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
  /** Simulation environment: "replay" | "reject_inference" (see app/envs). */
  env_id?: string;
  slice_dim: string | null;
  slice_value: string | null;
  language: Language;
  champion_ref?: string;
  challenger_ref?: string;
  beta_ref?: string | null;
  dataset_ref?: string;
  mapping_id?: string;
}

export interface CustomStrategy {
  id: string;
  name: string;
  version: string;
  role: string;
  required_inputs: string[];
  params: Record<string, { type: string; default: unknown; min?: number; max?: number }>;
  created_at: string;
}

export interface DatasetColumn {
  name: string;
  dtype: string;
  sample_values: string[];
}

export interface CustomDataset {
  id: string;
  name: string;
  n_rows: number;
  columns: DatasetColumn[];
  created_at: string;
}

export interface ColumnMapping {
  dataset_id: string;
  strategy_id: string;
  mapping: Record<string, string>;
  role_columns: Record<string, string>;
}

export interface MappingResult {
  id: string;
  available_layers: Record<'l1' | 'l2' | 'l3' | 'l4' | 'l5', boolean>;
  warnings: string[];
}

export interface KpiL1 { version: string; ks: number; auc: number; lift20: number; brier: number; }
export interface KpiL2 {
  version: string;
  approval_rate: number;
  avg_profit: number;
  raroc: number;
  el: number;
  /** Absolute scale — rates pick the winner, totals say if it is worth the cycle. */
  n_approved?: number;
  total_balance?: number;
  total_profit?: number;
  el_total?: number;
  economic_capital?: number;
  reason_coverage?: number;
}
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
  /** Which of the *champion's* rules declined each swap-in account. */
  swap_in_attribution?: GateAttribution[];
  /** Which of the *challenger's* rules declined each swap-out account. */
  swap_out_attribution?: GateAttribution[];
  swap_in_raroc?: number;
  swap_out_raroc?: number;
  rule_diff?: Array<{ param: string; champion: unknown; challenger: unknown }>;
}

export interface GainDecomposition {
  driver: 'model' | 'policy' | 'mixed';
  headline: string;
  total_swap_in: number;
  model_driven: { n: number; share: number; bad_rate: number | null; rules: GateAttribution[] };
  policy_driven: { n: number; share: number; bad_rate: number | null; rules: GateAttribution[] };
  swap_in_bad_rate?: number;
  swap_out_bad_rate?: number;
  swap_in_raroc?: number;
}

export interface RepairAttempt {
  value: number;
  run_id: string;
  cleared: boolean;
  introduced: string[];
  ok: boolean;
  metrics?: { approval_rate?: number; bad_rate?: number; raroc?: number; di?: Record<string, number> };
}

export interface RepairResult {
  run_id: string;
  finding: GuardrailFinding;
  knob: string;
  from: number;
  why: string;
  attempts: RepairAttempt[];
  fixed: RepairAttempt | null;
  diagnosis?: { dominant_reason: string; note: string | null; by_reason: Array<{ reason: string; group_pct: number; reference_pct: number; gap_pp: number }> } | null;
  note: string;
}

export interface EvidenceBundle {
  run_id: string;
  markdown: string;
  recommendation: { verdict: string; why: string; note?: string };
  open_questions: string[];
  replication_included: boolean;
  ri_comparison_included: boolean;
}

export interface GateAttribution {
  reason: string;
  rule: string;
  n: number;
  pct: number;
  bad_rate: number;
}

export interface GuardrailFinding {
  code: string;
  severity: 'block' | 'warn';
  detail: string;
  strategy?: string;
  value?: unknown;
  threshold?: number;
}

export interface GuardrailReport {
  run_id: string;
  ok: boolean;
  blocking: GuardrailFinding[];
  warnings: GuardrailFinding[];
}

export interface ReplicationReport {
  seeds: number[];
  n: number;
  stable: boolean | null;
  verdict: string;
  ranking_by_raroc?: { consistent: boolean | null; winner?: string | null; orders: string[][] };
  strategies: Record<string, Record<string, { mean: number; std: number; min: number; max: number; ci95: [number, number] | null; n: number }>>;
}

/** One phase event from POST /api/agent/investigate/stream. */
export interface AgentEvent {
  phase: string;
  [key: string]: unknown;
}

export interface L5Kpis { di_female_male: number; di_delta_vs_champ: number; tpr_gap: number; reason_coverage: number; }

export interface RiStrategyReport {
  n_swap_in: number;
  estimated_bad_rate?: number;
  oracle_bad_rate?: number;
  bias_pp?: number;
  relative_error?: number | null;
  direction?: string;
  note?: string;
}

/** The world a run assumed — and what it may NOT be used to claim. */
export interface RunEnvironment {
  id: string;
  version: string;
  level: string;
  name_zh: string;
  confidence: 'high' | 'medium' | 'low';
  valid_for: string[];
  not_valid_for: string[];
  note?: string;
  reject_inference?: {
    mode: string;
    n_observed: number;
    n_masked: number;
    max_relative_error: number | null;
    note: string;
    strategies: Record<string, RiStrategyReport>;
  };
}

export interface RunResult {
  run_id: string;
  /** True when this result came from demo fixtures because the API was unreachable. */
  demo?: boolean;
  champion: string;
  challenger: string;
  beta: string | null;
  sample_size: number;
  duration_s: number;
  snapshot_sha: string;
  /** Reproducibility hash: same manifest_sha => same numbers. */
  manifest_sha?: string;
  /** Lineage: a slice/variation is a NEW run derived from this one. */
  parent_run_id?: string | null;
  root_run_id?: string;
  created_by?: string;
  engine_version?: string;
  metric_version?: string;
  environment?: RunEnvironment;
  config: ExperimentConfig;
  layers: {
    l1: {
      kpis: KpiL1[];
      psi_monthly: Array<{ month: string; psi: number; tone: string }>;
      roc: Record<string, Array<{ fpr: number; tpr: number }>>;
      calibration: Record<string, Array<{ pd_pred: number; actual: number }>>;
      csi: Array<{ feature: string; csi: number }>;
      simulated_cohorts?: boolean;
      rank_ordering?: Record<string, Array<{ decile: number; n: number; bad_rate: number; pd_hat_mean: number }>>;
    };
    l2: {
      kpis: KpiL2[];
      totals?: Record<string, { n_approved: number; total_balance: number; total_profit: number; el_total: number; economic_capital: number }>;
      frontier: Array<Record<string, number>>;
      rejection_reasons: Record<string, Array<{ reason: string; pct: number }>>;
      raroc_bands: Record<string, Array<{ band: string; raroc: number }>>;
    };
    l3: {
      derived?: boolean;
      derived_from?: string;
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

export type Screen = 'config' | 'execution' | 'results' | 'history' | 'list' | 'strategies' | 'datasets' | 'agent';
export type ResultsTab = 'strategy' | 'metrics';
export type MetricsLayer = 'l1' | 'l2' | 'l3' | 'l4' | 'l5';

// ─── Experiment history ─────────────────────────────────────────────────────
// A run is never overwritten, so history is a tree of attempts, not a log.

export type RunVerdict = 'clean' | 'warned' | 'blocked' | 'unknown';

export interface RunHistoryItem {
  run_id: string;
  timestamp: string;
  champion: string;
  challenger: string;
  beta: string | null;
  sample_id: string;
  sample_size?: number;
  duration_s: number;
  l1_ks: number;
  l1_auc: number;
  l2_raroc: number;
  l2_approval_rate?: number | null;
  l2_bad_rate?: number | null;
  manifest_sha?: string | null;
  parent_run_id?: string | null;
  root_run_id?: string;
  created_by?: string;
  slice?: { dim: string | null; value: string | null };
  overrides?: Record<string, Record<string, number>>;
  environment?: string | null;
  hypothesis?: string | null;
  conclusion?: string | null;
  tags?: string[];
  verdict?: RunVerdict;
  blocking?: string[];
  warnings?: string[];
  /** True when this row came from demo fixtures, not the backend. */
  demo?: boolean;
}

export interface ExperimentTreeNode extends RunHistoryItem {
  depth: number;
}

export interface ExperimentTree {
  root_run_id: string;
  nodes: ExperimentTreeNode[];
  started_at: string;
  last_at: string;
  n_runs: number;
  n_blocked: number;
  n_clean: number;
  question: string | null;
  finding: string | null;
  champion: string;
  challenger: string;
  sample_id: string;
}

export interface DiffMetric {
  layer: MetricsLayer;
  key: string;
  role: 'champion' | 'challenger' | 'beta';
  strategy_a: string;
  strategy_b: string;
  label_zh: string;
  label_en: string;
  format: 'pct' | 'pct2' | 'num2' | 'num3' | 'num4' | 'money' | 'int';
  a: number | null;
  b: number | null;
  delta: number | null;
  better: 'a' | 'b' | null;
}

export interface RunDiff {
  a: RunHistoryItem;
  b: RunHistoryItem;
  same_manifest: boolean;
  note_zh: string;
  note_en: string;
  config_diff: Array<{ field: string; label_zh: string; label_en: string; a: unknown; b: unknown }>;
  metrics: DiffMetric[];
}
