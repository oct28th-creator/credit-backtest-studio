import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, Language, Strategy, ResultsTab, MetricsLayer, Sample } from '../types';
import StratChip from '../components/StratChip';
import SliceFilter from '../components/SliceFilter';
import L1Panel from './results/L1Panel';
import L2Panel from './results/L2Panel';
import L3Panel from './results/L3Panel';
import L4Panel from './results/L4Panel';
import L5Panel from './results/L5Panel';
import StrategyAnalysisScreen from './StrategyAnalysisScreen';
import API from '../api/client';
import { applyMockSlice } from '../data/mockData';

interface ResultsScreenProps {
  result: RunResult;
  strategies: Strategy[];
  samples: Sample[];
  language: Language;
  onResultUpdate: (r: RunResult) => void;
  onNewRun?: () => void;
  onGenerateReport?: () => void;
}

const LAYER_TABS: Array<{ key: MetricsLayer; labelKey: string }> = [
  { key: 'l1', labelKey: 'layer_l1' },
  { key: 'l2', labelKey: 'layer_l2' },
  { key: 'l3', labelKey: 'layer_l3' },
  { key: 'l4', labelKey: 'layer_l4' },
  { key: 'l5', labelKey: 'layer_l5' },
];

export default function ResultsScreen({ result, strategies, samples, language, onResultUpdate }: ResultsScreenProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<ResultsTab>('metrics');
  const [activeLayer, setActiveLayer] = useState<MetricsLayer>('l1');
  const [sliceDim, setSliceDim] = useState<string | null>(result.config.slice_dim);
  const [sliceValue, setSliceValue] = useState<string | null>(result.config.slice_value);
  const [slicing, setSlicing] = useState(false);

  const sample = samples.find(s => s.id === result.config.sample_id);

  async function handleSliceChange(dim: string | null, value: string | null) {
    setSliceDim(dim);
    setSliceValue(value);
    setSlicing(true);
    try {
      const updated = await API.reslice(result.run_id, { slice_dim: dim, slice_value: value });
      onResultUpdate(updated);
    } catch {
      const updated = applyMockSlice(result, { slice_dim: dim, slice_value: value });
      onResultUpdate(updated);
    } finally {
      setSlicing(false);
    }
  }

  const versions = [result.challenger, result.champion, ...(result.beta ? [result.beta] : [])];

  return (
    <div className="results-screen">
      {/* Top Info Bar */}
      <div className="results-info-bar">
        <div className="results-strat-chips">
          {versions.map(v => {
            const s = strategies.find(st => st.id === v);
            const role = v === result.challenger ? 'challenger' : v === result.champion ? 'champion' : 'beta';
            return s ? <StratChip key={v} id={v} role={role as 'challenger' | 'champion' | 'beta'} /> : null;
          })}
        </div>
        <div className="results-meta">
          <span className="meta-item">
            <span className="meta-label">{t('results_sample_info')}:</span>
            <span>{language === 'zh' ? sample?.name_zh : sample?.name_en}</span>
          </span>
          <span className="meta-sep">·</span>
          <span className="meta-item">
            <span className="meta-label">{t('results_sample_size')}:</span>
            <span>{result.sample_size.toLocaleString()}</span>
          </span>
          <span className="meta-sep">·</span>
          <span className="meta-item">
            <span className="meta-label">{t('results_run_id')}:</span>
            <code>{result.run_id}</code>
          </span>
          <span className="meta-sep">·</span>
          <span className="meta-item">
            <span className="meta-label">{t('results_sha')}:</span>
            <code>{result.snapshot_sha}</code>
          </span>
          {slicing && <span className="slicing-indicator"><span className="dots-spinner" /></span>}
        </div>
      </div>

      {/* Slice Filter */}
      <SliceFilter
        onSliceChange={handleSliceChange}
        currentDim={sliceDim}
        currentValue={sliceValue}
      />

      {/* Main Tabs */}
      <div className="main-tabs">
        <button
          className={`main-tab ${activeTab === 'strategy' ? 'main-tab-active' : ''}`}
          onClick={() => setActiveTab('strategy')}
          type="button"
        >
          🔍 {t('results_tab_strategy')}
        </button>
        <button
          className={`main-tab ${activeTab === 'metrics' ? 'main-tab-active' : ''}`}
          onClick={() => setActiveTab('metrics')}
          type="button"
        >
          📊 {t('results_tab_metrics')}
        </button>
      </div>

      {/* Strategy Analysis Tab */}
      {activeTab === 'strategy' && (
        <StrategyAnalysisScreen result={result} strategies={strategies} language={language} />
      )}

      {/* Metrics Tab */}
      {activeTab === 'metrics' && (
        <div className="metrics-panel">
          {/* Layer Tabs */}
          <div className="layer-tabs">
            {LAYER_TABS.map(tab => (
              <button
                key={tab.key}
                className={`layer-tab ${activeLayer === tab.key ? 'layer-tab-active' : ''}`}
                onClick={() => setActiveLayer(tab.key)}
                type="button"
              >
                {t(tab.labelKey)}
              </button>
            ))}
          </div>

          {/* Layer Content */}
          <div className="layer-content">
            {activeLayer === 'l1' && <L1Panel result={result} language={language} />}
            {activeLayer === 'l2' && <L2Panel result={result} language={language} />}
            {activeLayer === 'l3' && <L3Panel result={result} language={language} />}
            {activeLayer === 'l4' && <L4Panel result={result} language={language} />}
            {activeLayer === 'l5' && <L5Panel result={result} language={language} />}
          </div>
        </div>
      )}
    </div>
  );
}
