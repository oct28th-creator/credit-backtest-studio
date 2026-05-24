import React, { useState, useRef } from 'react';
import type { Strategy, Sample, ExperimentConfig, Language } from '../types';
import Icon from '../components/Icon';
import API from '../api/client';

interface ConfigScreenProps {
  strategies: Strategy[];
  samples: Sample[];
  language: Language;
  onRun: (config: ExperimentConfig) => void;
}

interface ParsedConfig {
  challenger?: string;
  champion?: string;
  beta?: string | null;
  sample_id?: string;
  lookback_months?: number;
  perf_window_months?: number;
  intent?: string;
  config_summary?: string;
  expected_results?: string;
  warnings?: string[];
  confidence?: number;
}

const SUGGESTIONS = [
  { chip: '大促场景', text: '对比 v2.2 v2.3 v2.4-Beta 在大促场景下的表现，重点看公平性和 swap-set' },
  { chip: '公平性专项', text: '跑 v2.3 vs v2.2，只看 DI Ratio 和公平性合规指标' },
  { chip: '全量对比', text: '三策略全量指标对比，包含 L1-L5 完整回测' },
];

export default function ConfigScreen({ strategies, samples, language, onRun }: ConfigScreenProps) {
  const [challenger, setChallenger] = useState<string>('v2.3');
  const [champion, setChampion] = useState<string>('v2.2');
  const [beta, setBeta] = useState<string | null>('v2.4-Beta');
  const [sampleId, setSampleId] = useState<string>(samples[0]?.id ?? '');
  const [lookback, setLookback] = useState(6);
  const [perfWin, setPerfWin] = useState(12);
  const [riMode, setRiMode] = useState('parceling');
  const [nl, setNl] = useState('');
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState<ParsedConfig | null>(null);
  const [thinking, setThinking] = useState('');
  const [thinkOpen, setThinkOpen] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  const sample = samples.find(s => s.id === sampleId);

  const runAi = (txt?: string) => {
    const text = (txt ?? nl).trim();
    if (!text) return;
    setParsing(true); setParsed(null); setThinking(''); setThinkOpen(true);
    cleanupRef.current?.();
    cleanupRef.current = API.streamParseConfig(
      text,
      language,
      (t) => setThinking(s => s + t),
      (chunk) => {
        try {
          const cfg = JSON.parse(chunk) as ParsedConfig;
          if (cfg.challenger) setChallenger(cfg.challenger);
          if (cfg.champion) setChampion(cfg.champion);
          if (cfg.beta !== undefined) setBeta(cfg.beta ?? null);
          if (cfg.sample_id) setSampleId(cfg.sample_id);
          if (cfg.lookback_months) setLookback(cfg.lookback_months);
          if (cfg.perf_window_months) setPerfWin(cfg.perf_window_months);
          setParsed(cfg);
        } catch { /* partial */ }
      },
      () => { setParsing(false); cleanupRef.current = null; },
      () => { setParsing(false); setParsed({ intent: '解析失败' }); cleanupRef.current = null; },
    );
  };

  const chalStrat = strategies.find(s => s.id === challenger);
  const champStrat = strategies.find(s => s.id === champion);
  const betaStrat = beta ? strategies.find(s => s.id === beta) : null;

  function handleRun() {
    if (!sampleId) return;
    const config: ExperimentConfig = {
      challenger,
      champion,
      beta,
      sample_id: sampleId,
      lookback_months: lookback,
      perf_window_months: perfWin,
      ri_mode: riMode,
      slice_dim: null,
      slice_value: null,
      language,
    };
    onRun(config);
  }

  return (
    <div className="page">
      <div className="page-hd">
        <div>
          <div className="page-title">新建回测实验</div>
          <div className="page-sub">配置策略、样本与回测参数，或使用自然语言一键描述需求</div>
        </div>
        <button className="btn primary lg" onClick={handleRun} type="button">
          <Icon name="play" size={12} /> 运行回测
        </button>
      </div>

      {/* AI Prompt */}
      <div className="mb16">
        <div className="ai-box">
          <textarea
            className="ai-ta"
            rows={2}
            value={nl}
            onChange={e => setNl(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runAi(); } }}
            placeholder="用自然语言描述回测需求，例如：对比 v2.3 和 v2.2 在大促场景下的公平性表现…"
            disabled={parsing}
          />
          <div className="ai-box-ft">
            <div className="ai-chips">
              {SUGGESTIONS.map(s => (
                <button
                  key={s.chip}
                  className="ai-chiptip"
                  type="button"
                  onClick={() => { setNl(s.text); setTimeout(() => runAi(s.text), 0); }}
                >
                  {s.chip}
                </button>
              ))}
            </div>
            <button className="ai-go" type="button" onClick={() => runAi()} disabled={parsing || !nl.trim()}>
              {parsing ? <span className="ai-spin" /> : <Icon name="sparkles" size={15} />}
            </button>
          </div>
        </div>

        {(thinking || parsing) && !parsed && (
          <div className="mt8 thinking">
            <div className="think-hd" onClick={() => setThinkOpen(v => !v)}>
              {parsing ? <span className="think-spin" /> : <span className="think-dot" style={{ background: thinking ? 'var(--green)' : 'var(--ink-4)' }} />}
              <span style={{ flex: 1 }}>{parsing ? '正在思考…' : '已完成推理'}</span>
              <span className="think-arrow" style={{ transform: thinkOpen ? 'rotate(90deg)' : 'rotate(0deg)' }}>▶</span>
            </div>
            {thinkOpen && thinking && (
              <div className="think-body">
                <div className="think-text">{thinking}</div>
              </div>
            )}
          </div>
        )}

        {parsed && (
          <div className="ai-preview">
            <div className="ai-preview-hd">
              <Icon name="sparkles" size={13} /> AI 解析结果
              {parsed.confidence != null && <span className="ai-conf">置信度 {Math.round(parsed.confidence * 100)}%</span>}
            </div>
            {thinking && (
              <div className="thinking mb8">
                <div className="think-hd" onClick={() => setThinkOpen(v => !v)}>
                  <span className="think-dot" style={{ background: 'var(--green)' }} />
                  <span style={{ flex: 1 }}>已完成推理</span>
                  <span className="think-arrow" style={{ transform: thinkOpen ? 'rotate(90deg)' : 'rotate(0deg)' }}>▶</span>
                </div>
                {thinkOpen && (
                  <div className="think-body">
                    <div className="think-text">{thinking}</div>
                  </div>
                )}
              </div>
            )}
            {parsed.intent && <div className="ai-prow"><span className="ai-plbl">意图</span><span className="ai-pval">{parsed.intent}</span></div>}
            {parsed.config_summary && <div className="ai-prow"><span className="ai-plbl">配置</span><span className="ai-pval">{parsed.config_summary}</span></div>}
            {parsed.expected_results && <div className="ai-prow"><span className="ai-plbl">预期</span><span className="ai-pval">{parsed.expected_results}</span></div>}
            {parsed.warnings && parsed.warnings.length > 0 && (
              <div className="ai-prow">
                <span className="ai-plbl" style={{ background: 'var(--amber-s)', color: 'var(--amber)' }}>注意</span>
                <span className="ai-pval">{parsed.warnings.join(' · ')}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Strategy comparison config */}
      <div className="card mb16">
        <div className="card-hd">
          <div>
            <div className="card-title">策略对比配置</div>
            <div className="card-sub">挑战者与基线已锁定为生产环境配置，可加选 β 策略进行三方对比</div>
          </div>
        </div>
        <div className="card-body">
          <div className="cmp-grid">
            {/* Challenger — locked */}
            <div className="cmp-card chal">
              <div className="cmp-card-hd">
                <span className="cmp-role"><span className="cmp-dot" /> 挑战者</span>
                <span className="cmp-sub">本次回测主体</span>
                <span className="cmp-lock"><Icon name="lock" size={12} /></span>
              </div>
              {chalStrat?.nickname && <div className="cmp-prod">{chalStrat.nickname}</div>}
              <div className="cmp-ver">{challenger}</div>
              <div className="cmp-desc">{language === 'zh' ? chalStrat?.desc_zh : chalStrat?.desc_en}</div>
            </div>

            {/* Champion / baseline — locked */}
            <div className="cmp-card champ">
              <div className="cmp-card-hd">
                <span className="cmp-role"><span className="cmp-dot" /> 基线策略</span>
                <span className="cmp-sub">当前生产策略</span>
                <span className="cmp-lock"><Icon name="lock" size={12} /></span>
              </div>
              {champStrat?.nickname && <div className="cmp-prod">{champStrat.nickname}</div>}
              <div className="cmp-ver">{champion}</div>
              {champStrat?.online_since && <div className="cmp-meta">上线 {champStrat.online_since} · 线上生产策略</div>}
              <div className="cmp-desc">{language === 'zh' ? champStrat?.desc_zh : champStrat?.desc_en}</div>
            </div>

            {/* Beta — optional / selectable */}
            {beta && betaStrat ? (
              <div className="cmp-card beta">
                <div className="cmp-card-hd">
                  <span className="cmp-role"><span className="cmp-dot" /> 对照 β</span>
                  <button className="cmp-remove" type="button" onClick={() => setBeta(null)}>
                    <Icon name="x" size={11} /> 移除对照组
                  </button>
                </div>
                <select
                  className="sel cmp-select"
                  value={beta}
                  onChange={e => setBeta(e.target.value)}
                >
                  {strategies.filter(s => s.id !== challenger && s.id !== champion).map(s => (
                    <option key={s.id} value={s.id}>{s.id}{s.nickname ? ` — ${s.nickname}` : ''}</option>
                  ))}
                </select>
                <div className="cmp-desc">{language === 'zh' ? betaStrat.desc_zh : betaStrat.desc_en}</div>
              </div>
            ) : (
              <button
                className="cmp-add"
                type="button"
                onClick={() => {
                  const first = strategies.find(s => s.id !== challenger && s.id !== champion);
                  if (first) setBeta(first.id);
                }}
              >
                <span className="cmp-add-icon"><Icon name="plus" size={20} /></span>
                <div className="cmp-add-title">加选 β 策略</div>
                <div className="cmp-add-sub">可选 · 用于第三方对比</div>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Sample + window */}
      <div className="g2" style={{ gridTemplateColumns: '1.5fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div className="card-hd">
            <div>
              <div className="card-title">
                数据集 <span className="tag green" style={{ marginLeft: 6 }}>不可变快照</span>
              </div>
              <div className="card-sub">版本锁定，保证可复现性</div>
            </div>
          </div>
          <div className="card-body">
            <div className="flex" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              {samples.map(s => (
                <button
                  key={s.id}
                  type="button"
                  className={`slice-chip ${sampleId === s.id ? 'on' : ''}`}
                  onClick={() => setSampleId(s.id)}
                >
                  {sampleId === s.id && '✓ '}{language === 'zh' ? s.name_zh : s.name_en}
                  <span className="muted" style={{ marginLeft: 6, fontSize: 11 }}>{(s.n_rows / 1000).toFixed(0)}k 条</span>
                </button>
              ))}
            </div>
            {sample && (
              <div className="text-xs muted" style={{ lineHeight: 1.7 }}>
                <strong className="bold" style={{ color: 'var(--ink-2)' }}>{language === 'zh' ? sample.name_zh : sample.name_en}</strong> · {language === 'zh' ? sample.product_mix_zh : sample.product_mix_en}<br />
                {language === 'zh' ? sample.channels_zh : sample.channels_en}<br />
                {language === 'zh' ? sample.desc_zh : sample.desc_en}
              </div>
            )}
            <div className="divider" />
            <div className="g3" style={{ gap: 12 }}>
              <div>
                <div className="text-xs muted bold" style={{ marginBottom: 4 }}>回溯窗口</div>
                <select className="sel" value={lookback} onChange={e => setLookback(+e.target.value)}>
                  <option value={3}>近 3 个月</option>
                  <option value={6}>近 6 个月</option>
                  <option value={12}>近 12 个月</option>
                </select>
              </div>
              <div>
                <div className="text-xs muted bold" style={{ marginBottom: 4 }}>绩效观察窗</div>
                <select className="sel" value={perfWin} onChange={e => setPerfWin(+e.target.value)}>
                  <option value={6}>M6</option>
                  <option value={12}>M12</option>
                  <option value={18}>M18</option>
                </select>
              </div>
              <div>
                <div className="text-xs muted bold" style={{ marginBottom: 4 }}>样本量</div>
                <div className="num" style={{ fontSize: 18, fontWeight: 700 }}>
                  {sample ? (sample.n_rows / 1000).toFixed(0) + 'k' : '—'}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-hd"><div className="card-title">收益归因模式</div></div>
          <div className="card-body">
            {[
              { val: 'parceling', title: '差额分摊（推荐）', sub: '将 Challenger 相对 Champion 的增量收益/损失分摊至决策差异样本' },
              { val: 'accept_only', title: '仅通过客群', sub: '只考察两套策略均通过的客群，适合严格 A/B 场景' },
            ].map(opt => (
              <div
                key={opt.val}
                className={`ri-opt ${riMode === opt.val ? 'on' : ''}`}
                onClick={() => setRiMode(opt.val)}
              >
                <input type="radio" checked={riMode === opt.val} readOnly style={{ marginTop: 2, flexShrink: 0 }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>
                    {opt.title} {opt.val === 'parceling' && <span className="tag blue" style={{ marginLeft: 4 }}>推荐</span>}
                  </div>
                  <div className="text-xs muted" style={{ marginTop: 4 }}>{opt.sub}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
