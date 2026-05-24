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

async function postStream(
  path: string,
  body: Record<string, unknown>,
  { onThink, onResult, onDone, onErr }: StreamHandler
): Promise<() => void> {
  const controller = new AbortController();
  (async () => {
    try {
      const res = await fetch(`/api${path}`, {
        method: 'POST',
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (line.startsWith('data:')) {
            const payload = line.slice(5).trim();
            if (payload === '[DONE]') { onDone(); return; }
            try {
              const obj = JSON.parse(payload) as { type: string; content?: string };
              if (obj.type === 'thinking') onThink(obj.content ?? '');
              else if (obj.type === 'text') onResult(obj.content ?? '');
            } catch { /* skip malformed */ }
          }
        }
      }
      onDone();
    } catch (e) {
      if ((e as Error).name !== 'AbortError') onErr(e as Error);
    }
  })();
  return () => controller.abort();
}

function openStream(
  path: string,
  { onThink, onResult, onDone, onErr }: StreamHandler
): () => void {
  const es = new EventSource(`/api${path}`);
  es.addEventListener('thinking', (e: MessageEvent) => onThink((e as MessageEvent).data as string));
  es.addEventListener('text', (e: MessageEvent) => onResult((e as MessageEvent).data as string));
  es.addEventListener('done', () => { es.close(); onDone(); });
  es.onerror = (e) => { es.close(); onErr(new Error('SSE error: ' + JSON.stringify(e))); };
  return () => es.close();
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
  startReal: (h: StreamHandler) => Promise<() => void>,
  mockThink: string,
  mockResult: string,
  h: StreamHandler,
): () => void {
  let cancelled = false;
  let gotData = false;
  let realAbort: (() => void) | null = null;
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

  startReal(wrapped)
    .then((abort) => { realAbort = abort; if (cancelled) abort(); })
    .catch(() => { if (!cancelled && !gotData) mockAbort = mockStream(mockThink, mockResult, h); });

  return () => { cancelled = true; realAbort?.(); mockAbort?.(); };
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
      return await apiFetch<StrategiesResponse>('/strategies');
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
      return await apiFetch<RunResult>('/run', { method: 'POST', body: JSON.stringify(config) }, 120000);
    } catch {
      await delay(2000);
      return MOCK_RUN_RESULT;
    }
  },

  async reslice(runId: string, sliceConfig: { slice_dim: string | null; slice_value: string | null }): Promise<RunResult> {
    try {
      return await apiFetch<RunResult>(`/run/${runId}/reslice`, { method: 'POST', body: JSON.stringify(sliceConfig) });
    } catch {
      return applyMockSlice(MOCK_RUN_RESULT, sliceConfig);
    }
  },

  async getRun(runId: string): Promise<RunResult> {
    try {
      return await apiFetch<RunResult>(`/run/${runId}`);
    } catch {
      return MOCK_RUN_RESULT;
    }
  },

  async listRuns(): Promise<RunHistoryItem[]> {
    try {
      return await apiFetch<RunHistoryItem[]>('/runs');
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
      (h) => postStream('/ai/parse-config', { text, lang }, h),
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
    const MOCK_THINKS: Record<string, string> = {
      l1: '正在分析模型判别能力指标，对比挑战者与基准组的 KS、AUC 差异，检查 PSI 稳定性，评估 Brier Score 校准质量...',
      l2: '正在评估业务价值层，分析审批率提升的风险收益权衡，计算 RAROC 各评分段分布，审查拒绝原因结构变化...',
      l3: '正在分析风险表现，对比 MOB12 不良率趋势，检查 M1→M2 滚动率异常，评估 FPD 月度波动...',
      l4: '正在分析换客群矩阵，评估挑战者换入换出客群的质量差异，计算决策一致性并进行显著性检验...',
      l5: '正在评估公平性指标，检查各人口统计群体的 DI 比率，分析 SHAP 特征权重是否存在偏见风险...',
      strategy: '正在对比挑战者与基线策略的规则差异：评分卡权重、DTI 限额、评分截断、反欺诈版本与决策表分流，定位导致换客群与收益差异的关键规则变更...',
    };
    const MOCK_RESULTS: Record<string, string> = {
      l1: JSON.stringify({
        findings: ['v2.3 KS=0.48，较基准 v2.2 提升14.3%，判别能力显著改善', 'AUC 从0.78提升至0.83，Lift@20%达到3.2x', 'PSI 全月稳定在0.10以下，特征分布无明显漂移'],
        warnings: ['查询次数(6月)特征CSI=0.11，接近预警阈值，需关注'],
        recommendations: ['建议在高分段进一步验证校准精度', '可考虑对 CSI>0.10 的特征做版本监控'],
      }),
      l2: JSON.stringify({
        findings: ['v2.3 审批率38%，较基准提升10pp，RAROC达22%，业务价值显著', 'Pareto前沿显示v2.3处于效率边界上', '高分段(740+) RAROC高达40%，低DTI段收益最优'],
        warnings: ['v2.4-Beta审批率45%但RAROC仅16%，扩张代价高'],
        recommendations: ['建议将v2.3的660-700分段审批参数作为推广候选', '评估在DTI 0.20-0.35段加大力度的可行性'],
      }),
      l3: JSON.stringify({
        findings: ['v2.3 MOB12不良率2.4%，可接受范围内', 'FPD率3.2%与同期基准差距约0.7pp，在预期内', 'M1→M2滚动率18%，高于基准15%，需跟踪'],
        warnings: ['v2.4-Beta不良率3.2%，M1→M2滚动率22%，风险明显偏高'],
        recommendations: ['建议对滚动率较高的渠道细分进行专项风控', '下个月关注MOB6至MOB12的加速情况'],
      }),
      l4: JSON.stringify({
        findings: ['v2.3 vs v2.2 一致性96.5%，仅3240个换入、2610个换出客户', '换出客群不良率仅0.9%，远低于换入客群4.8%，质量差异显著', 'p值=0.012，一致性差异统计显著'],
        warnings: ['v2.4-Beta vs v2.2 一致性仅89.1%，大量边缘案例决策不一致'],
        recommendations: ['建议重点审查580-620分段的换入案例质量', '对一致性<95%的评分段设置额外人工复核'],
      }),
      l5: JSON.stringify({
        findings: ['v2.3 DI女/男=0.86，高于监管红线0.80', '理由覆盖率94%，可解释性良好', 'SHAP显示决策主要由还款历史驱动，无明显偏见特征'],
        warnings: ['v2.4-Beta年轻客群DI=0.77，低于监管红线0.80！需要立即审查'],
        recommendations: ['建议对v2.4-Beta进行公平性改进后再考虑上线', '对DI<0.85的群体建立月度监控报告机制'],
      }),
      strategy: JSON.stringify({
        findings: [
          'v2.3 相对 v2.2 升级了评分卡：放宽 DTI 限额 0.40→0.45、下调评分截断 640→620，整体更激进地获取中高分客群',
          '反欺诈引擎由 AF-v2 升级至 AF-v3，新增社交网络欺诈图谱与申请速率限制规则',
          '决策表在 660-700 分段对挑战者放量，是换入客群与审批率提升的主要来源',
        ],
        warnings: ['v2.4-Beta 进一步将 DTI 放宽至 0.50、截断降至 600，扩张激进，需重点核查其风险与公平性代价'],
        recommendations: [
          '挑战者 v2.3 的规则变更与收益提升因果清晰，建议推进上线审批',
          '保留 v2.2 决策表作为高风险分段的回退基线，便于异常时快速切换',
        ],
      }),
    };
    return streamWithFallback(
      (h) => postStream(`/ai/analyze/${runId}/${layer}`, { lang }, h),
      MOCK_THINKS[layer] ?? '正在分析...',
      MOCK_RESULTS[layer] ?? '{}',
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
    return streamWithFallback(
      (h) => postStream(`/ai/chat/${runId}`, { msg, history, layer, lang }, h),
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
        (h) => postStream(`/ai/report/${runId}`, { lang }, h),
        lang === 'zh' ? '正在生成回测报告，汇总 L1-L5 各层分析结论与策略建议…' : 'Generating the report, consolidating L1-L5 findings and recommendations…',
        reportMd,
        { onThink, onResult: onChunk, onDone, onErr },
      );
    }
  },
};

export default API;
