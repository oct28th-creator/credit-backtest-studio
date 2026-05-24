import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
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
  { chipKey: 'cfg_sug_promo', textKey: 'cfg_sug_promo_text' },
  { chipKey: 'cfg_sug_fairness', textKey: 'cfg_sug_fairness_text' },
  { chipKey: 'cfg_sug_full', textKey: 'cfg_sug_full_text' },
];

export default function ConfigScreen({ strategies, samples, language, onRun }: ConfigScreenProps) {
  const { t } = useTranslation();
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
    let resultBuf = '';
    cleanupRef.current = API.streamParseConfig(
      text,
      language,
      (t) => setThinking(s => s + t),
      (chunk) => {
        resultBuf += chunk;
        try {
          const cfg = JSON.parse(resultBuf) as ParsedConfig;
          if (cfg.challenger) setChallenger(cfg.challenger);
          if (cfg.champion) setChampion(cfg.champion);
          if (cfg.beta !== undefined) setBeta(cfg.beta ?? null);
          if (cfg.sample_id) setSampleId(cfg.sample_id);
          if (cfg.lookback_months) setLookback(cfg.lookback_months);
          if (cfg.perf_window_months) setPerfWin(cfg.perf_window_months);
          setParsed(cfg);
        } catch { /* accumulating partial JSON */ }
      },
      () => { setParsing(false); cleanupRef.current = null; },
      () => { setParsing(false); setParsed({ intent: t('error_ai') }); cleanupRef.current = null; },
    );
  };

  const chalStrat = strategies.find(s => s.id === challenger);
  const champStrat = strategies.find(s => s.id === champion);
  const betaStrat = beta ? strategies.find(s => s.id === beta) : null;
  const nick = (s?: Strategy | null) => s ? (language === 'en' ? (s.nickname_en ?? s.nickname) : s.nickname) : '';

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
          <div className="page-title">{t('cfg_title')}</div>
          <div className="page-sub">{t('cfg_sub')}</div>
        </div>
        <button className="btn primary lg" onClick={handleRun} type="button">
          <Icon name="play" size={12} /> {t('cfg_run')}
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
            placeholder={t('cfg_nl_placeholder')}
            disabled={parsing}
          />
          <div className="ai-box-ft">
            <div className="ai-chips">
              {SUGGESTIONS.map(s => (
                <button
                  key={s.chipKey}
                  className="ai-chiptip"
                  type="button"
                  onClick={() => { const txt = t(s.textKey); setNl(txt); setTimeout(() => runAi(txt), 0); }}
                >
                  {t(s.chipKey)}
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
              <span style={{ flex: 1 }}>{parsing ? t('cfg_thinking') : t('cfg_think_done')}</span>
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
              <Icon name="sparkles" size={13} /> {t('cfg_parse_result')}
              {parsed.confidence != null && <span className="ai-conf">{t('cfg_confidence')} {Math.round(parsed.confidence * 100)}%</span>}
            </div>
            {thinking && (
              <div className="thinking mb8">
                <div className="think-hd" onClick={() => setThinkOpen(v => !v)}>
                  <span className="think-dot" style={{ background: 'var(--green)' }} />
                  <span style={{ flex: 1 }}>{t('cfg_think_done')}</span>
                  <span className="think-arrow" style={{ transform: thinkOpen ? 'rotate(90deg)' : 'rotate(0deg)' }}>▶</span>
                </div>
                {thinkOpen && (
                  <div className="think-body">
                    <div className="think-text">{thinking}</div>
                  </div>
                )}
              </div>
            )}
            {parsed.intent && <div className="ai-prow"><span className="ai-plbl">{t('cfg_intent')}</span><span className="ai-pval">{parsed.intent}</span></div>}
            {parsed.config_summary && <div className="ai-prow"><span className="ai-plbl">{t('cfg_config')}</span><span className="ai-pval">{parsed.config_summary}</span></div>}
            {parsed.expected_results && <div className="ai-prow"><span className="ai-plbl">{t('cfg_expected')}</span><span className="ai-pval">{parsed.expected_results}</span></div>}
            {parsed.warnings && parsed.warnings.length > 0 && (
              <div className="ai-prow">
                <span className="ai-plbl" style={{ background: 'var(--amber-s)', color: 'var(--amber)' }}>{t('cfg_note')}</span>
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
            <div className="card-title">{t('cfg_strat_title')}</div>
            <div className="card-sub">{t('cfg_strat_sub')}</div>
          </div>
        </div>
        <div className="card-body">
          <div className="cmp-grid">
            {/* Challenger — locked */}
            <div className="cmp-card chal">
              <div className="cmp-card-hd">
                <span className="cmp-role"><span className="cmp-dot" /> {t('cfg_role_challenger')}</span>
                <span className="cmp-sub">{t('cfg_challenger_sub')}</span>
                <span className="cmp-lock"><Icon name="lock" size={12} /></span>
              </div>
              {chalStrat?.nickname && <div className="cmp-prod">{nick(chalStrat)}</div>}
              <div className="cmp-ver">{challenger}</div>
              <div className="cmp-desc">{language === 'zh' ? chalStrat?.desc_zh : chalStrat?.desc_en}</div>
            </div>

            {/* Champion / baseline — locked */}
            <div className="cmp-card champ">
              <div className="cmp-card-hd">
                <span className="cmp-role"><span className="cmp-dot" /> {t('cfg_role_baseline')}</span>
                <span className="cmp-sub">{t('cfg_baseline_sub')}</span>
                <span className="cmp-lock"><Icon name="lock" size={12} /></span>
              </div>
              {champStrat?.nickname && <div className="cmp-prod">{nick(champStrat)}</div>}
              <div className="cmp-ver">{champion}</div>
              {champStrat?.online_since && <div className="cmp-meta">{t('cfg_online_prefix')} {champStrat.online_since} · {t('cfg_online_prod')}</div>}
              <div className="cmp-desc">{language === 'zh' ? champStrat?.desc_zh : champStrat?.desc_en}</div>
            </div>

            {/* Beta — optional / selectable */}
            {beta && betaStrat ? (
              <div className="cmp-card beta">
                <div className="cmp-card-hd">
                  <span className="cmp-role"><span className="cmp-dot" /> {t('cfg_role_beta')}</span>
                  <button className="cmp-remove" type="button" onClick={() => setBeta(null)}>
                    <Icon name="x" size={11} /> {t('cfg_remove_beta')}
                  </button>
                </div>
                <select
                  className="sel cmp-select"
                  value={beta}
                  onChange={e => setBeta(e.target.value)}
                >
                  {strategies.filter(s => s.id !== challenger && s.id !== champion).map(s => (
                    <option key={s.id} value={s.id}>{s.id}{s.nickname ? ` — ${nick(s)}` : ''}</option>
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
                <div className="cmp-add-title">{t('cfg_add_beta')}</div>
                <div className="cmp-add-sub">{t('cfg_add_beta_sub')}</div>
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
                {t('cfg_dataset')} <span className="tag green" style={{ marginLeft: 6 }}>{t('cfg_snapshot')}</span>
              </div>
              <div className="card-sub">{t('cfg_dataset_sub')}</div>
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
                  <span className="muted" style={{ marginLeft: 6, fontSize: 11 }}>{(s.n_rows / 1000).toFixed(0)}k {t('cfg_rows_unit')}</span>
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
                <div className="text-xs muted bold" style={{ marginBottom: 4 }}>{t('cfg_lookback')}</div>
                <select className="sel" value={lookback} onChange={e => setLookback(+e.target.value)}>
                  <option value={3}>{t('cfg_lookback_3')}</option>
                  <option value={6}>{t('cfg_lookback_6')}</option>
                  <option value={12}>{t('cfg_lookback_12')}</option>
                </select>
              </div>
              <div>
                <div className="text-xs muted bold" style={{ marginBottom: 4 }}>{t('cfg_perf_window')}</div>
                <select className="sel" value={perfWin} onChange={e => setPerfWin(+e.target.value)}>
                  <option value={6}>M6</option>
                  <option value={12}>M12</option>
                  <option value={18}>M18</option>
                </select>
              </div>
              <div>
                <div className="text-xs muted bold" style={{ marginBottom: 4 }}>{t('cfg_sample_size')}</div>
                <div className="num" style={{ fontSize: 18, fontWeight: 700 }}>
                  {sample ? (sample.n_rows / 1000).toFixed(0) + 'k' : '—'}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-hd"><div className="card-title">{t('cfg_ri_title')}</div></div>
          <div className="card-body">
            {[
              { val: 'parceling', titleKey: 'cfg_ri_parceling', subKey: 'cfg_ri_parceling_sub' },
              { val: 'accept_only', titleKey: 'cfg_ri_accept', subKey: 'cfg_ri_accept_sub' },
            ].map(opt => (
              <div
                key={opt.val}
                className={`ri-opt ${riMode === opt.val ? 'on' : ''}`}
                onClick={() => setRiMode(opt.val)}
              >
                <input type="radio" checked={riMode === opt.val} readOnly style={{ marginTop: 2, flexShrink: 0 }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>
                    {t(opt.titleKey)} {opt.val === 'parceling' && <span className="tag blue" style={{ marginLeft: 4 }}>{t('cfg_recommended')}</span>}
                  </div>
                  <div className="text-xs muted" style={{ marginTop: 4 }}>{t(opt.subKey)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
