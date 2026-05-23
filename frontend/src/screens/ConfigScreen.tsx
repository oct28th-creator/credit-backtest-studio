import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { Strategy, Sample, ExperimentConfig, Language } from '../types';
import Icon from '../components/Icon';
import StratChip from '../components/StratChip';
import API from '../api/client';

interface ConfigScreenProps {
  strategies: Strategy[];
  samples: Sample[];
  language: Language;
  onRun: (config: ExperimentConfig) => void;
}

const LAYER_OPTIONS = [
  { key: 'l1', labelKey: 'layer_l1' },
  { key: 'l2', labelKey: 'layer_l2' },
  { key: 'l3', labelKey: 'layer_l3' },
  { key: 'l4', labelKey: 'layer_l4' },
  { key: 'l5', labelKey: 'layer_l5' },
];

export default function ConfigScreen({ strategies, samples, language, onRun }: ConfigScreenProps) {
  const { t } = useTranslation();
  const [intent, setIntent] = useState('');
  const [parsing, setParsing] = useState(false);
  const [sampleId, setSampleId] = useState<string>(samples[0]?.id ?? '');
  const [showBeta, setShowBeta] = useState(true);
  const [betaId, setBetaId] = useState<string>('v2.4-Beta');
  const [selectedLayers, setSelectedLayers] = useState<string[]>(['l1', 'l2', 'l3', 'l4', 'l5']);
  const cleanupRef = useRef<(() => void) | null>(null);

  const challenger = strategies.find(s => s.role === 'challenger') ?? strategies[0];
  const champion = strategies.find(s => s.role === 'champion') ?? strategies[1];
  const betaOptions = strategies.filter(s => s.role === 'beta');

  function handleParseIntent() {
    if (!intent.trim()) return;
    setParsing(true);
    if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null; }

    const cleanup = API.streamParseConfig(
      intent,
      language,
      () => {},
      (chunk) => {
        try {
          const parsed = JSON.parse(chunk) as { sample_id?: string; show_beta?: boolean };
          if (parsed.sample_id) setSampleId(parsed.sample_id);
          if (parsed.show_beta !== undefined) setShowBeta(parsed.show_beta);
        } catch { /* partial chunk */ }
      },
      () => { setParsing(false); cleanupRef.current = null; },
      () => { setParsing(false); cleanupRef.current = null; }
    );
    cleanupRef.current = cleanup;
  }

  function toggleLayer(key: string) {
    setSelectedLayers(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  }

  function handleRun() {
    if (!sampleId) return;
    const sample = samples.find(s => s.id === sampleId);
    const config: ExperimentConfig = {
      challenger: challenger?.id ?? 'v2.3',
      champion: champion?.id ?? 'v2.2',
      beta: showBeta ? betaId : null,
      sample_id: sampleId,
      lookback_months: sample?.lookback_months ?? 12,
      perf_window_months: sample?.perf_window_months ?? 12,
      ri_mode: 'standard',
      slice_dim: null,
      slice_value: null,
      language,
    };
    onRun(config);
  }

  return (
    <div className="config-screen">
      {/* Intent Section */}
      <section className="config-section">
        <div className="section-label">{t('config_intent_label')}</div>
        <div className="intent-row">
          <textarea
            className="intent-input"
            placeholder={t('config_intent_placeholder')}
            value={intent}
            onChange={e => setIntent(e.target.value)}
            rows={3}
          />
          <button
            className="btn-ai-trigger"
            onClick={handleParseIntent}
            disabled={parsing || !intent.trim()}
            type="button"
          >
            {parsing ? (
              <><span className="dots-spinner" />{t('config_parsing')}</>
            ) : (
              <><Icon name="sparkles" size={15} />{t('config_intent_btn')}</>
            )}
          </button>
        </div>
      </section>

      {/* Strategy Selection */}
      <section className="config-section">
        <div className="section-label">{t('config_strategy_title')}</div>
        <div className="strategy-layout">
          {/* Challenger */}
          <div className="strategy-card strategy-card-challenger">
            <div className="strategy-card-header">
              <StratChip id={challenger?.id ?? 'v2.3'} role="challenger" />
              <span className="locked-badge">
                <Icon name="lock" size={12} />
                {t('config_locked')}
              </span>
            </div>
            <div className="strategy-card-name">{challenger?.name}</div>
            <div className="strategy-card-desc">
              {language === 'zh' ? challenger?.desc_zh : challenger?.desc_en}
            </div>
            <div className="strategy-card-meta">
              <span>DTI ≤{((challenger?.dti_limit ?? 0.45) * 100).toFixed(0)}%</span>
              <span>·</span>
              <span>{t('strategy_score_cutoff')}: {challenger?.score_cutoff}</span>
            </div>
          </div>

          {/* VS Badge */}
          <div className="vs-badge">{t('config_vs_badge')}</div>

          {/* Champion + Beta */}
          <div className="champion-beta-col">
            {/* Champion */}
            <div className="strategy-card strategy-card-champion">
              <div className="strategy-card-header">
                <StratChip id={champion?.id ?? 'v2.2'} role="champion" />
                <span className="locked-badge">
                  <Icon name="lock" size={12} />
                  {t('config_locked')}
                </span>
              </div>
              <div className="strategy-card-name">{champion?.name}</div>
              <div className="strategy-card-desc">
                {language === 'zh' ? champion?.desc_zh : champion?.desc_en}
              </div>
              <div className="strategy-card-meta">
                <span>DTI ≤{((champion?.dti_limit ?? 0.40) * 100).toFixed(0)}%</span>
                <span>·</span>
                <span>{t('strategy_score_cutoff')}: {champion?.score_cutoff}</span>
              </div>
            </div>

            {/* Beta */}
            {showBeta ? (
              <div className="strategy-card strategy-card-beta">
                <div className="strategy-card-header">
                  <StratChip id={betaId} role="beta" />
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => setShowBeta(false)}
                    type="button"
                  >
                    <Icon name="x" size={12} />
                    {t('config_remove_beta')}
                  </button>
                </div>
                <select
                  className="beta-select"
                  value={betaId}
                  onChange={e => setBetaId(e.target.value)}
                >
                  {betaOptions.map(b => (
                    <option key={b.id} value={b.id}>{b.id} — {language === 'zh' ? b.desc_zh : b.desc_en}</option>
                  ))}
                </select>
              </div>
            ) : (
              <button
                className="add-beta-btn"
                onClick={() => { setShowBeta(true); setBetaId(betaOptions[0]?.id ?? 'v2.4-Beta'); }}
                type="button"
              >
                <Icon name="plus" size={16} />
                {t('config_add_beta')}
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Sample Selection */}
      <section className="config-section">
        <div className="section-label">{t('config_sample_title')}</div>
        <div className="sample-grid">
          {samples.map(sample => (
            <label key={sample.id} className={`sample-card ${sampleId === sample.id ? 'sample-card-selected' : ''}`}>
              <input
                type="radio"
                name="sample"
                value={sample.id}
                checked={sampleId === sample.id}
                onChange={() => setSampleId(sample.id)}
                style={{ display: 'none' }}
              />
              <div className="sample-card-name">
                {language === 'zh' ? sample.name_zh : sample.name_en}
              </div>
              <div className="sample-card-meta">
                <span className="sample-meta-row">
                  <span className="sample-meta-label">{t('sample_vintage')}:</span>
                  <span>{sample.vintage}</span>
                </span>
                <span className="sample-meta-row">
                  <span className="sample-meta-label">{t('sample_rows')}:</span>
                  <span>{sample.n_rows.toLocaleString()}</span>
                </span>
                <span className="sample-meta-row">
                  <span className="sample-meta-label">{t('sample_lookback')}:</span>
                  <span>{sample.lookback_months}{t('sample_months')}</span>
                </span>
                <span className="sample-meta-row">
                  <span className="sample-meta-label">{t('sample_perf_window')}:</span>
                  <span>{sample.perf_window_months}{t('sample_months')}</span>
                </span>
              </div>
              <div className="sample-card-desc">
                {language === 'zh' ? sample.desc_zh : sample.desc_en}
              </div>
            </label>
          ))}
        </div>
      </section>

      {/* Metrics Selection */}
      <section className="config-section">
        <div className="section-label">{t('config_metrics_title')}</div>
        <div className="metrics-checkboxes">
          {LAYER_OPTIONS.map(layer => (
            <label key={layer.key} className={`metric-checkbox ${selectedLayers.includes(layer.key) ? 'metric-checkbox-checked' : ''}`}>
              <input
                type="checkbox"
                checked={selectedLayers.includes(layer.key)}
                onChange={() => toggleLayer(layer.key)}
                style={{ display: 'none' }}
              />
              <span className="metric-checkbox-box">
                {selectedLayers.includes(layer.key) && <Icon name="check" size={12} />}
              </span>
              {t(layer.labelKey)}
            </label>
          ))}
        </div>
      </section>

      {/* Run Button */}
      <div className="config-run-row">
        <button
          className="btn-primary btn-lg"
          onClick={handleRun}
          disabled={!sampleId || selectedLayers.length === 0}
          type="button"
        >
          <Icon name="play" size={18} />
          {t('config_run_btn')}
        </button>
      </div>
    </div>
  );
}
