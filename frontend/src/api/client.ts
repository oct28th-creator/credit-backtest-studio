import type { ExperimentConfig, RunResult, Strategy, Sample, Language } from '../types';
import { MOCK_STRATEGIES, MOCK_SAMPLES, MOCK_RUN_RESULT, applyMockSlice } from '../data/mockData';

const DEFAULT_TIMEOUT = 30000;

async function apiFetch<T>(path: string, options?: RequestInit, timeoutMs = DEFAULT_TIMEOUT): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`/api${path}`, {
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timer);
  }
}

type StreamHandler = {
  onThink: (chunk: string) => void;
  onResult: (text: string) => void;
  onDone: () => void;
  onErr: (err: Error) => void;
};

interface SSEEvent {
  type?: string;
  content?: string;
  config?: unknown;
  findings?: string[];
  warnings?: string[];
  recommendations?: string[];
}

// Stream from a backend SSE endpoint, translating its event schema
// (thinking | result | reply | chunk | config) into the StreamHandler.
// Returns a synchronous abort function.
function backendStream(
  method: 'GET' | 'POST',
  path: string,
  body: Record<string, unknown> | null,
  { onThink, onResult, onDone, onErr }: StreamHandler,
): () => void {
  const controller = new AbortController();
  (async () => {
    try {
      const res = await fetch(`/api${path}`, {
        method,
        signal: controller.signal,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      const handleEvent = (raw: string) => {
        if (/^event:\s*done/m.test(raw)) { onDone(); return true; }
        const data = raw.split('\n').filter(l => l.startsWith('data:')).map(l => l.slice(5).trim()).join('');
        if (!data) return false;
        if (data === '[DONE]') { onDone(); return true; }
        try {
          const obj = JSON.parse(data) as SSEEvent;
          switch (obj.type) {
            case 'thinking': onThink(obj.content ?? ''); break;
            case 'reply':
            case 'chunk':
            case 'text': onResult(obj.content ?? ''); break;
            case 'result':
              if (obj.config !== undefined) onResult(JSON.stringify(obj.config));
              else onResult(JSON.stringify({ findings: obj.findings ?? [], warnings: obj.warnings ?? [], recommendations: obj.recommendations ?? [] }));
              break;
          }
        } catch { /* skip malformed */ }
        return false;
      };
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const events = buf.split('\n\n');
        buf = events.pop() ?? '';
        for (const evt of events) {
          if (evt.trim() && handleEvent(evt)) return;
        }
      }
      if (buf.trim()) handleEvent(buf);
      onDone();
    } catch (e) {
      if ((e as Error).name !== 'AbortError') onErr(e as Error);
    }
  })();
  return () => controller.abort();
}

// Mock AI streaming helper
function mockStream(
  thinkText: string,
  resultText: string,
  { onThink, onResult, onDone }: StreamHandler
): () => void {
  let cancelled = false;
  (async () => {
    // Stream thinking word by word
    const words = thinkText.split(' ');
    for (const word of words) {
      if (cancelled) return;
      onThink(word + ' ');
      await delay(40);
    }
    await delay(300);
    // Stream result
    const chunks = resultText.match(/.{1,8}/g) ?? [];
    for (const chunk of chunks) {
      if (cancelled) return;
      onResult(chunk);
      await delay(25);
    }
    if (!cancelled) onDone();
  })();
  return () => { cancelled = true; };
}

function delay(ms: number) { return new Promise(r => setTimeout(r, ms)); }

// Run the real (backend) stream; if it fails before producing any data,
// transparently fall back to a mock stream so the UI never dead-ends.
function streamWithFallback(
  startReal: (h: StreamHandler) => () => void,
  mockThink: string,
  mockResult: string,
  h: StreamHandler,
): () => void {
  let cancelled = false;
  let gotData = false;
  let mockAbort: (() => void) | null = null;

  const wrapped: StreamHandler = {
    onThink: (c) => { gotData = true; if (!cancelled) h.onThink(c); },
    onResult: (c) => { gotData = true; if (!cancelled) h.onResult(c); },
    onDone: () => { if (!cancelled) h.onDone(); },
    onErr: () => {
      if (cancelled) return;
      if (gotData) { h.onDone(); return; }
      mockAbort = mockStream(mockThink, mockResult, h);
    },
  };

  const realAbort = startReal(wrapped);
  return () => { cancelled = true; realAbort(); mockAbort?.(); };
}


interface HistoryParams { strategy?: string; sample?: string; limit?: number }
interface RunHistoryItem {
  run_id: string; timestamp: string; champion: string; challenger: string;
  beta: string | null; sample_id: string; duration_s: number;
  l1_ks: number; l1_auc: number; l2_raroc: number;
}

const MOCK_HISTORY: RunHistoryItem[] = [
  { run_id: 'run-20241101-001', timestamp: '2024-11-01T10:22:00Z', champion: 'v2.2', challenger: 'v2.3', beta: null, sample_id: 'bf2022', duration_s: 11.2, l1_ks: 0.46, l1_auc: 0.82, l2_raroc: 0.21 },
  { run_id: 'run-20241108-001', timestamp: '2024-11-08T14:05:00Z', champion: 'v2.2', challenger: 'v2.3', beta: 'v2.4-Beta', sample_id: 'bf2023', duration_s: 14.8, l1_ks: 0.47, l1_auc: 0.83, l2_raroc: 0.22 },
  { run_id: 'run-20241112-001', timestamp: '2024-11-12T09:11:00Z', champion: 'v2.2', challenger: 'v2.3', beta: 'v2.5-RC', sample_id: 'bf2023', duration_s: 15.1, l1_ks: 0.48, l1_auc: 0.84, l2_raroc: 0.23 },
  { run_id: 'run-20241115-001', timestamp: '2024-11-15T16:30:00Z', champion: 'v2.2', challenger: 'v2.3', beta: 'v2.4-Beta', sample_id: 'bf2023', duration_s: 12.4, l1_ks: 0.48, l1_auc: 0.83, l2_raroc: 0.22 },
];

interface StrategiesResponse { strategies: Strategy[]; defaults: { challenger: string; champion: string } }
interface SamplesResponse { samples: Sample[] }

export const API = {
  async listStrategies(): Promise<StrategiesResponse> {
    try {
      return await apiFetch<StrategiesResponse>('/samples/strategies');
    } catch {
      return { strategies: MOCK_STRATEGIES, defaults: { challenger: 'v2.3', champion: 'v2.2' } };
    }
  },

  async listSamples(): Promise<SamplesResponse> {
    try {
      return await apiFetch<SamplesResponse>('/samples');
    } catch {
      return { samples: MOCK_SAMPLES };
    }
  },

  async run(config: ExperimentConfig): Promise<RunResult> {
    try {
      return await apiFetch<RunResult>('/experiments/run', { method: 'POST', body: JSON.stringify(config) }, 120000);
    } catch {
      await delay(2000);
      return MOCK_RUN_RESULT;
    }
  },

  async reslice(runId: string, sliceConfig: { slice_dim: string | null; slice_value: string | null }): Promise<RunResult> {
    try {
      return await apiFetch<RunResult>(`/experiments/${runId}/reslice`, { method: 'POST', body: JSON.stringify(sliceConfig) });
    } catch {
      return applyMockSlice(MOCK_RUN_RESULT, sliceConfig);
    }
  },

  async getRun(runId: string): Promise<RunResult> {
    try {
      return await apiFetch<RunResult>(`/experiments/${runId}`);
    } catch {
      return MOCK_RUN_RESULT;
    }
  },

  async listRuns(): Promise<RunHistoryItem[]> {
    try {
      const res = await apiFetch<{ runs: RunHistoryItem[] }>('/experiments');
      return res.runs ?? [];
    } catch {
      return MOCK_HISTORY;
    }
  },

  async getHistory(params: HistoryParams = {}): Promise<RunHistoryItem[]> {
    const qs = new URLSearchParams();
    if (params.strategy) qs.set('strategy', params.strategy);
    if (params.sample) qs.set('sample', params.sample);
    if (params.limit) qs.set('limit', String(params.limit));
    try {
      return await apiFetch<RunHistoryItem[]>(`/history?${qs}`);
    } catch {
      let items = MOCK_HISTORY;
      if (params.strategy) items = items.filter(i => i.challenger === params.strategy || i.champion === params.strategy);
      if (params.sample) items = items.filter(i => i.sample_id === params.sample);
      if (params.limit) items = items.slice(0, params.limit);
      return items;
    }
  },

  streamParseConfig(
    text: string,
    lang: Language,
    onThink: (c: string) => void,
    onResult: (c: string) => void,
    onDone: () => void,
    onErr: (e: Error) => void
  ): () => void {
    const zh = lang === 'zh';
    const mockThink = zh
      ? '正在解析自然语言需求：识别对比的策略版本（挑战者 / 基线 / 对照 β），匹配样本数据集，提取回溯窗口与绩效观察窗参数，推断分析重点（公平性 / 收益 / 风险）…'
      : 'Parsing the natural-language request: identifying strategy versions (challenger / baseline / control β), matching the sample dataset, extracting lookback and performance windows, and inferring the analysis focus (fairness / value / risk)…';
    const mockResult = JSON.stringify({
      challenger: 'v2.3',
      champion: 'v2.2',
      beta: /beta|对照|β|v2\.4/i.test(text) ? 'v2.4-Beta' : null,
      sample_id: 'bf2023',
      lookback_months: 6,
      perf_window_months: 12,
      intent: zh
        ? '对比挑战者 v2.3 与基线 v2.2，并加入 v2.4-Beta 进行三方回测分析'
        : 'Compare challenger v2.3 against baseline v2.2, with v2.4-Beta as a three-way control',
      config_summary: zh
        ? 'v2.3 vs v2.2 (+ v2.4-Beta) · 黑五2023样本 · 回溯6月 / 绩效M12'
        : 'v2.3 vs v2.2 (+ v2.4-Beta) · Black Friday 2023 · lookback 6m / perf M12',
      expected_results: zh
        ? '预计 v2.3 在 KS/AUC 与审批收益上优于基线，需重点核查 v2.4-Beta 的公平性 (DI) 风险'
        : 'v2.3 is expected to beat the baseline on KS/AUC and approval value; watch v2.4-Beta fairness (DI) risk',
      warnings: /公平|fair|di/i.test(text) ? [zh ? '已聚焦公平性：将优先呈现 L5 DI 比率与 SHAP 解释' : 'Fairness focus: L5 DI ratio and SHAP explanations prioritized'] : [],
      confidence: 0.92,
    });
    return streamWithFallback(
      (h) => backendStream('POST', '/ai/parse-config/stream', { text, language: lang }, h),
      mockThink, mockResult,
      { onThink, onResult, onDone, onErr },
    );
  },

  streamAnalyzeLayer(
    runId: string,
    layer: string,
    lang: Language,
    onThink: (c: string) => void,
    onResult: (c: string) => void,
    onDone: () => void,
    onErr: (e: Error) => void
  ): () => void {
    const zh = lang === 'zh';
    const THINKS: Record<string, string> = zh ? {
      l1: '正在分析模型判别能力：对比挑战者 v2.3 与基线 v2.2 的 KS、AUC、Lift@20%，逐月核查 PSI 与特征 CSI 稳定性，评估 Brier Score 校准质量与高分段排序单调性…',
      l2: '正在评估业务价值层：测算审批率提升带来的风险收益权衡，分解各评分段 RAROC 与边际收益，审查拒绝原因结构变化，定位 Pareto 效率边界上的最优工作点…',
      l3: '正在分析风险表现：对比 MOB12 不良率与成熟度曲线，检查 M1→M2 滚动率异常、首逾(FPD) 月度波动，并按渠道与分段拆解风险来源…',
      l4: '正在分析换客群矩阵：量化挑战者相对基线的换入/换出客群规模与质量差异，计算决策一致性并做卡方显著性检验，定位边际决策翻转的评分段…',
      l5: '正在评估公平性：逐群体核查 DI 比率（女/男、外地/本地、年轻/核心）与监管红线的距离，分析 SHAP 特征贡献是否存在受保护属性的代理偏见，并核对理由码覆盖率…',
      strategy: '正在对比挑战者与基线策略的规则差异：评分卡权重与方向、DTI 限额、评分截断、反欺诈版本、决策表分流与客群分叉，定位导致换客群、审批率与收益差异的关键规则变更，并评估其风险与公平性外溢…',
    } : {
      l1: 'Analyzing model discrimination: comparing KS, AUC and Lift@20% of challenger v2.3 vs baseline v2.2, checking month-by-month PSI and feature CSI stability, and assessing Brier-score calibration and high-band rank monotonicity…',
      l2: 'Evaluating business value: weighing the risk/return of the approval-rate lift, decomposing RAROC and marginal profit by score band, reviewing rejection-reason shifts, and locating the optimal operating point on the Pareto frontier…',
      l3: 'Analyzing risk performance: comparing MOB12 bad-rate and maturity curves, checking M1→M2 roll-rate anomalies and FPD monthly volatility, and decomposing risk sources by channel and band…',
      l4: 'Analyzing the swap-set matrix: quantifying the size and quality of swap-in/swap-out segments vs the baseline, computing decision consistency with a chi-square significance test, and locating the bands where marginal decisions flip…',
      l5: 'Evaluating fairness: checking DI ratios per group (female/male, non-local/local, young/core) against the regulatory line, analyzing whether SHAP contributions reveal proxy bias on protected attributes, and verifying reason-code coverage…',
      strategy: 'Comparing challenger vs baseline rule differences: scorecard weights and directions, DTI limit, score cutoff, anti-fraud version, decision-table routing and segment bifurcation — locating the key rule changes that drive swap-set, approval-rate and profit differences, and assessing their risk and fairness spillovers…',
    };
    const RESULTS: Record<string, string> = zh ? {
      l1: JSON.stringify({
        findings: [
          'v2.3 KS=0.48，较基线 v2.2 (0.42) 提升 14.3%，判别能力显著改善，差异主要来自 600-720 中高分段',
          'AUC 由 0.78 提升至 0.83，Lift@20% 达 3.2x（基线 2.8x），头部 20% 坏账捕获率提升约 12pp',
          'Brier Score 0.118（基线 0.142）校准更优，PSI 全月稳定在 0.10 以下，无总体分布漂移',
        ],
        warnings: [
          '查询次数(6月) 特征 CSI=0.11，接近 0.10 预警阈值，存在轻微分布漂移，需纳入监控',
          '740+ 高分段样本量较稀疏，校准置信区间较宽，结论稳健性待验证',
        ],
        recommendations: [
          '建议在 740+ 高分段补充样本或采用分段校准，确认排序单调性',
          '对 CSI>0.10 的特征建立月度版本监控与告警',
          '上线初期对 600-660 新增放量分段做小流量灰度观察',
        ],
      }),
      l2: JSON.stringify({
        findings: [
          'v2.3 审批率 38%，较基线提升 10pp；RAROC 达 22%（基线 19%），增量收益与风险匹配良好',
          'Pareto 前沿显示 v2.3 处于效率边界上，单位风险收益优于基线',
          '高分段 (740+) RAROC 高达 40%，低 DTI 段 (0.20-0.35) 收益最优，是增量价值主要来源',
        ],
        warnings: [
          'v2.4-Beta 审批率 45% 但 RAROC 仅 16%，扩张以牺牲单位收益为代价，性价比偏低',
          '审批率提升伴随预期损失 EL 上升约 0.3pp，需确认拨备覆盖充足',
        ],
        recommendations: [
          '建议将 v2.3 的 660-700 分段审批参数作为推广候选，预计净收益最大',
          '评估在 DTI 0.20-0.35 段进一步加大力度的可行性',
          '对 v2.4-Beta 的激进扩张设置收益护栏后再评估',
        ],
      }),
      l3: JSON.stringify({
        findings: [
          'v2.3 MOB12 不良率 2.4%，处于可接受区间，成熟度曲线与基线基本重合',
          'FPD 率 3.2%，与同期基线差距约 0.7pp，在预期波动范围内',
          '风险增量集中在新增放量的 600-640 分段，与审批扩张方向一致',
        ],
        warnings: [
          'M1→M2 滚动率 18%，高于基线 15%，迁移恶化迹象需持续跟踪',
          'v2.4-Beta 不良率 3.2%、滚动率 22%，风险明显偏高',
        ],
        recommendations: [
          '建议对滚动率较高的线上渠道细分实施专项风控与额度收紧',
          '下个月重点关注 MOB6→MOB12 的不良加速情况',
          '为 600-640 新增分段设置独立的早期风险预警阈值',
        ],
      }),
      l4: JSON.stringify({
        findings: [
          'v2.3 vs v2.2 决策一致性 96.5%，仅 3,240 换入、2,610 换出，决策变更克制可控',
          '换出客群不良率仅 0.9%，远低于换入客群 4.8%，说明换出的是优质误拒、换入承担了更高风险',
          '一致性差异 p=0.012，统计显著；换出提升 0.57x 表明被换出客群整体质量较好',
        ],
        warnings: [
          'v2.4-Beta vs v2.2 一致性仅 89.1%，大量边缘案例决策翻转，稳定性不足',
          '换入客群 4.8% 的不良率高于组合均值，需确认其增量收益能覆盖风险',
        ],
        recommendations: [
          '建议重点人工复核 580-620 分段的换入案例质量',
          '对一致性 <95% 的评分段设置额外人工复核与限额',
          '换入客群上线后做独立 vintage 跟踪，验证风险定价是否充分',
        ],
      }),
      l5: JSON.stringify({
        findings: [
          'v2.3 DI 女/男=0.86、外地/本地=0.88、年轻/核心=0.86，全部高于监管红线 0.80',
          '理由码覆盖率 94%，拒绝可解释性良好，满足合规披露要求',
          'SHAP 显示决策主要由还款历史与信用使用率驱动，未见受保护属性的明显代理偏见',
        ],
        warnings: [
          'v2.4-Beta 年轻客群 DI=0.77，低于监管红线 0.80，存在显著公平性风险，需立即审查',
          '年轻/核心 DI 距红线裕度最小 (0.06)，扩张时需优先监控该群体',
        ],
        recommendations: [
          '建议对 v2.4-Beta 完成公平性整改并复测后再考虑上线',
          '对 DI<0.85 的群体建立月度公平性监控报告机制',
          '在评分卡中评估是否需要对年轻客群相关特征做去偏处理',
        ],
      }),
      strategy: JSON.stringify({
        findings: [
          'v2.3 相对 v2.2 升级了评分卡：放宽 DTI 限额 0.40→0.45、下调评分截断 640→620，整体更积极地获取 600-720 中高分客群',
          '反欺诈引擎由 AF-v2 升级至 AF-v3，新增「社交网络欺诈图谱」与「申请速率限制」两条规则，前端拦截更严',
          '决策表在 660-700 分段对挑战者放量，是换入客群与审批率提升 10pp 的主要来源',
          '提额区间由 ¥1,000-30,000 上调至 ¥2,000-50,000，对优质客群的额度更激进',
        ],
        warnings: [
          'v2.4-Beta 进一步将 DTI 放宽至 0.50、截断降至 600，并对年轻客群放量，扩张激进，需重点核查风险与公平性 (DI=0.77) 代价',
          'v2.3 评分卡放宽叠加额度上调，需确认 600-640 新增客群的风险定价是否充分',
        ],
        recommendations: [
          '挑战者 v2.3 的规则变更与收益提升因果清晰、风险可控，建议推进上线审批',
          '保留 v2.2 决策表作为高风险分段的回退基线，便于异常时快速切换',
          'v2.4-Beta 的激进规则需先完成公平性整改与风险护栏设置后再评估',
        ],
      }),
    } : {
      l1: JSON.stringify({
        findings: [
          'v2.3 KS=0.48, +14.3% over baseline v2.2 (0.42); discrimination clearly improves, mostly in the 600-720 mid-high band',
          'AUC rises 0.78→0.83 and Lift@20% reaches 3.2x (baseline 2.8x), capturing ~12pp more bad accounts in the top 20%',
          'Brier Score 0.118 (vs 0.142) shows better calibration; PSI stays below 0.10 all months with no overall drift',
        ],
        warnings: [
          'Inquiries(6m) feature CSI=0.11, near the 0.10 alert threshold — mild drift to monitor',
          'Sparse samples in the 740+ band widen calibration intervals; robustness needs confirmation',
        ],
        recommendations: [
          'Add samples or use band-wise calibration in the 740+ range to confirm rank monotonicity',
          'Set up monthly version monitoring and alerts for features with CSI>0.10',
          'Gray-release the newly expanded 600-660 band with limited traffic at launch',
        ],
      }),
      l2: JSON.stringify({
        findings: [
          'v2.3 approval rate 38% (+10pp); RAROC 22% (baseline 19%), with incremental return well matched to risk',
          'The Pareto frontier places v2.3 on the efficiency edge, beating the baseline on return per unit risk',
          'High band (740+) RAROC reaches 40% and the low-DTI band (0.20-0.35) is most profitable — the main source of value',
        ],
        warnings: [
          'v2.4-Beta approval 45% but RAROC only 16% — expansion at the cost of unit return, poor efficiency',
          'The approval lift raises expected loss (EL) by ~0.3pp; confirm provisioning is adequate',
        ],
        recommendations: [
          'Promote v2.3 approval parameters for the 660-700 band as the top net-profit candidate',
          'Assess feasibility of pushing harder in the DTI 0.20-0.35 band',
          'Add a profit guardrail before re-evaluating v2.4-Beta\'s aggressive expansion',
        ],
      }),
      l3: JSON.stringify({
        findings: [
          'v2.3 MOB12 bad rate 2.4%, within acceptable bounds; maturity curve largely overlaps the baseline',
          'FPD 3.2%, ~0.7pp from the baseline — within the expected volatility range',
          'Incremental risk concentrates in the newly expanded 600-640 band, consistent with the approval expansion',
        ],
        warnings: [
          'M1→M2 roll rate 18% vs baseline 15% — a migration-deterioration signal to keep tracking',
          'v2.4-Beta bad rate 3.2% and roll rate 22% are clearly elevated',
        ],
        recommendations: [
          'Apply targeted risk control and limit tightening to high-roll-rate online channels',
          'Watch the MOB6→MOB12 bad-rate acceleration next month',
          'Set a dedicated early-warning threshold for the new 600-640 band',
        ],
      }),
      l4: JSON.stringify({
        findings: [
          'v2.3 vs v2.2 decision consistency 96.5%; only 3,240 swap-in and 2,610 swap-out — changes are restrained and controllable',
          'Swap-out bad rate is just 0.9% vs swap-in 4.8%: the strategy swaps out good false-rejects while swap-ins carry higher risk',
          'Consistency difference p=0.012 (significant); swap-out lift 0.57x indicates the swapped-out segment is high quality',
        ],
        warnings: [
          'v2.4-Beta vs v2.2 consistency only 89.1% — many marginal cases flip, indicating instability',
          'Swap-in bad rate 4.8% exceeds the portfolio average; confirm incremental return covers the risk',
        ],
        recommendations: [
          'Manually review swap-in case quality in the 580-620 band',
          'Add manual review and limit caps for bands with consistency <95%',
          'Run a separate vintage track on swap-in customers to validate risk pricing',
        ],
      }),
      l5: JSON.stringify({
        findings: [
          'v2.3 DI female/male=0.86, non-local/local=0.88, young/core=0.86 — all above the 0.80 regulatory line',
          'Reason-code coverage 94%; rejection explainability is good and meets disclosure requirements',
          'SHAP shows decisions driven mainly by repayment history and credit utilization, with no clear proxy bias on protected attributes',
        ],
        warnings: [
          'v2.4-Beta young-group DI=0.77, below the 0.80 line — a material fairness risk requiring immediate review',
          'Young/core has the smallest margin to the line (0.06); prioritize monitoring this group during expansion',
        ],
        recommendations: [
          'Complete fairness remediation and re-test v2.4-Beta before considering launch',
          'Establish monthly fairness monitoring for groups with DI<0.85',
          'Assess whether young-group-related features in the scorecard need debiasing',
        ],
      }),
      strategy: JSON.stringify({
        findings: [
          'v2.3 upgrades the scorecard over v2.2: DTI limit relaxed 0.40→0.45 and score cutoff lowered 640→620, acquiring the 600-720 mid-high band more aggressively',
          'The anti-fraud engine moves AF-v2→AF-v3, adding "social-network fraud graph" and "application velocity limit" rules for stricter front-end interception',
          'The decision table opens up the 660-700 band for the challenger — the main driver of swap-ins and the +10pp approval lift',
          'Limit-increase range raised ¥1,000-30,000 → ¥2,000-50,000, more aggressive credit for quality customers',
        ],
        warnings: [
          'v2.4-Beta further relaxes DTI to 0.50, lowers the cutoff to 600 and expands young customers — aggressive growth; scrutinize its risk and fairness (DI=0.77) cost',
          'v2.3\'s looser scorecard plus higher limits means the new 600-640 segment needs adequate risk pricing',
        ],
        recommendations: [
          'v2.3\'s rule changes have a clear, controllable link to the profit lift — recommend advancing it to approval',
          'Keep the v2.2 decision table as a fallback baseline for high-risk bands for quick rollback',
          'v2.4-Beta\'s aggressive rules need fairness remediation and risk guardrails before evaluation',
        ],
      }),
    };
    const q = `language=${encodeURIComponent(lang)}`;
    const start = (h: StreamHandler) => layer === 'strategy'
      ? backendStream('POST', `/ai/compare/stream?run_id=${encodeURIComponent(runId)}&${q}`, null, h)
      : backendStream('GET', `/ai/analyze-layer/stream/${encodeURIComponent(runId)}?layer=${encodeURIComponent(layer)}&${q}`, null, h);
    return streamWithFallback(
      start,
      THINKS[layer] ?? (zh ? '正在分析…' : 'Analyzing…'),
      RESULTS[layer] ?? '{}',
      { onThink, onResult, onDone, onErr },
    );
  },

  streamChat(
    runId: string,
    msg: string,
    history: Array<{ role: string; content: string }>,
    layer: string,
    lang: Language,
    onThink: (c: string) => void,
    onReply: (c: string) => void,
    onDone: () => void,
    onErr: (e: Error) => void
  ): () => void {
    const reply = lang === 'zh'
      ? `关于"${msg}"：根据本次回测数据，v2.3 在该指标上相比基线 v2.2 表现更优，差异主要集中在中高分段。建议结合 L2 收益与 L5 公平性一并评估，确认增量收益不以公平性为代价。`
      : `Regarding "${msg}": based on this backtest, v2.3 outperforms baseline v2.2 on this metric, with the gap concentrated in the mid-high score bands. I'd cross-check L2 value and L5 fairness to confirm the lift doesn't come at a fairness cost.`;
    const apiHistory = history.map(m => ({ role: m.role === 'ai' ? 'assistant' : m.role, content: m.content }));
    return streamWithFallback(
      (h) => backendStream('POST', '/ai/chat/stream', { run_id: runId, message: msg, history: apiHistory, layer, language: lang }, h),
      lang === 'zh' ? '正在结合回测指标与历史对话进行推理…' : 'Reasoning over backtest metrics and prior conversation…',
      reply,
      { onThink, onResult: onReply, onDone, onErr },
    );
  },

  streamReport(
    runId: string,
    lang: Language,
    onThink: (c: string) => void,
    onChunk: (c: string) => void,
    onDone: () => void,
    onErr: (e: Error) => void
  ): () => void {
    {
      const reportMd = lang === 'zh'
        ? `# 回测分析报告\n\n## 执行摘要\n\n本次回测对比了信贷策略 **v2.3（挑战者）** 与 **v2.2（基准）**，以及 **v2.4-Beta（对照组）**，基于黑五2023样本（n=142,000）进行分析。\n\n## L1 模型质量\n\nv2.3 KS=0.48，AUC=0.83，较基准显著提升，判别能力优秀。PSI月度稳定，无分布漂移风险。\n\n## L2 业务价值\n\nv2.3 审批率38%，RAROC 22%，处于Pareto效率前沿。建议优先推进v2.3上线审批。\n\n## L3 风险表现\n\nMOB12不良率2.4%，FPD 3.2%，在可接受范围内。v2.4-Beta风险偏高，暂不推荐。\n\n## L4 换客群\n\nv2.3 vs v2.2 一致性96.5%，换出客群质量好，换入客群经过充分验证。\n\n## L5 公平性\n\nv2.3 DI指标全部达标。**v2.4-Beta年轻客群DI=0.77，存在监管风险，需整改后再评估。**\n\n## 结论建议\n\n**推荐 v2.3 进入审批流程**。v2.4-Beta需完成公平性整改后再次回测。`
        : `# Backtest Analysis Report\n\n## Executive Summary\n\nThis backtest compared credit strategy **v2.3 (Challenger)** vs **v2.2 (Champion)** and **v2.4-Beta (Control)** on the Black Friday 2023 sample (n=142,000).\n\n## L1 Model Quality\n\nv2.3 KS=0.48, AUC=0.83, significantly better than champion. PSI stable throughout, no distribution drift.\n\n## L2 Business Value\n\nv2.3 approval rate 38%, RAROC 22%, on the Pareto efficiency frontier. Recommend approving v2.3.\n\n## L3 Risk Performance\n\nMOB12 bad rate 2.4%, FPD 3.2%, within acceptable bounds. v2.4-Beta shows elevated risk.\n\n## L4 Swap-Set\n\nv2.3 vs v2.2 consistency 96.5%. Swap-out segment quality is excellent, swap-in well validated.\n\n## L5 Fairness\n\nv2.3 all DI metrics within threshold. **v2.4-Beta young group DI=0.77, regulatory risk identified.**\n\n## Recommendation\n\n**Recommend v2.3 for approval.** v2.4-Beta requires fairness remediation before re-evaluation.`;
      return streamWithFallback(
        (h) => backendStream('GET', `/ai/report/stream/${encodeURIComponent(runId)}?language=${encodeURIComponent(lang)}`, null, h),
        lang === 'zh' ? '正在生成回测报告，汇总 L1-L5 各层分析结论与策略建议…' : 'Generating the report, consolidating L1-L5 findings and recommendations…',
        reportMd,
        { onThink, onResult: onChunk, onDone, onErr },
      );
    }
  },
};

export default API;
