import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, Language } from '../../types';
import { useAI } from '../../hooks/useAI';
import KpiCard from '../../components/KpiCard';
import AiPanel from '../../components/AiPanel';
import { DiRatioChart, ShapChart } from '../../components/Chart';
import Icon from '../../components/Icon';
import API from '../../api/client';

interface L5PanelProps {
  result: RunResult;
  language: Language;
}

export default function L5Panel({ result, language }: L5PanelProps) {
  const { t } = useTranslation();
  const ai = useAI();
  const [showAi, setShowAi] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState(result.challenger);

  const l5 = result.layers.l5;
  const versions = [result.challenger, result.champion, ...(result.beta ? [result.beta] : [])];

  // Determine worst DI for alert
  const diGroups = l5.di_by_group[selectedStrategy];
  const minDI = diGroups ? Math.min(diGroups.female_male, diGroups.outsider_local, diGroups.young_core) : 1;

  const alertLevel = minDI < 0.80 ? 'red' : minDI < 0.85 ? 'amber' : null;

  function triggerAI() {
    setShowAi(true);
    ai.trigger((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l5', language, onThink, onResult, onDone, onErr)
    );
  }

  function rerunAI() {
    ai.rerun((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l5', language, onThink, onResult, onDone, onErr)
    );
  }

  const diChartData = diGroups ? [
    { label: t('l5_female_male'), value: diGroups.female_male },
    { label: t('l5_outsider_local'), value: diGroups.outsider_local },
    { label: t('l5_young_core'), value: diGroups.young_core },
  ] : [];

  const shapData = l5.shap[selectedStrategy] ?? [];

  return (
    <div className="layer-panel">
      {/* Alert Banner */}
      {alertLevel && (
        <div className={`alert ${alertLevel}`}>
          <span className="alert-icon"><Icon name="warn" size={18} /></span>
          <div className="alert-sub">
            {alertLevel === 'red' ? t('l5_alert_red') : t('l5_alert_amber')}
          </div>
        </div>
      )}

      <div className="layer-panel-header">
        <h3 className="layer-panel-title">{t('layer_l5_full')}</h3>
        <p className="layer-panel-desc">{t('l5_desc')}</p>
        {!showAi && (
          <button className="btn-ai-trigger" onClick={triggerAI} type="button">
            <Icon name="sparkles" size={15} />
            {t('ai_trigger')}
            <span className="ai-badge">{t('ai_badge')}</span>
          </button>
        )}
      </div>

      {/* KPI Cards */}
      <div className="kpi-grid">
        <KpiCard
          label={t('kpi_di_female_male')}
          value={l5.kpis.di_female_male.toFixed(2)}
          delta={l5.kpis.di_female_male - 0.80}
          higherIsBetter={true}
          highlight
        />
        <KpiCard
          label={t('kpi_di_delta')}
          value={l5.kpis.di_delta_vs_champ >= 0 ? `+${l5.kpis.di_delta_vs_champ.toFixed(2)}` : l5.kpis.di_delta_vs_champ.toFixed(2)}
          higherIsBetter={true}
          delta={l5.kpis.di_delta_vs_champ}
        />
        <KpiCard
          label={t('kpi_tpr_gap')}
          value={l5.kpis.tpr_gap.toFixed(3)}
          higherIsBetter={false}
          delta={-l5.kpis.tpr_gap}
        />
        <KpiCard
          label={t('kpi_reason_coverage')}
          value={`${(l5.kpis.reason_coverage * 100).toFixed(0)}%`}
          higherIsBetter={true}
          delta={l5.kpis.reason_coverage - 0.90}
        />
      </div>

      {/* Strategy Switcher */}
      <div className="version-tabs" style={{ marginBottom: 16 }}>
        <span style={{ fontSize: 12, color: 'var(--ink-4)', marginRight: 8 }}>{t('l5_strategy_switch')}:</span>
        {versions.map(v => {
          const vGroups = l5.di_by_group[v];
          const vMin = vGroups ? Math.min(vGroups.female_male, vGroups.outsider_local, vGroups.young_core) : 1;
          return (
            <button
              key={v}
              className={`version-tab ${selectedStrategy === v ? 'version-tab-active' : ''}`}
              onClick={() => setSelectedStrategy(v)}
              type="button"
            >
              {v}
              {vMin < 0.80 && <Icon name="warn" size={12} style={{ color: 'var(--red)', marginLeft: 4 }} />}
            </button>
          );
        })}
      </div>

      {/* Charts */}
      <div className="chart-grid chart-grid-2">
        <div className="chart-card">
          <div className="chart-title">{t('chart_di_title')} — {selectedStrategy}</div>
          <DiRatioChart groups={diChartData} />
          <div style={{ fontSize: 11, color: 'var(--red)', marginTop: 6 }}>
            — {t('l5_threshold_label')}
          </div>
        </div>
        <div className="chart-card">
          <div className="chart-title">{t('chart_shap_title')} — {selectedStrategy}</div>
          <ShapChart data={shapData} />
        </div>
      </div>

      {/* DI All Strategies Table */}
      <div className="chart-card">
        <div className="chart-title">{t('l5_di_groups')}</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>{language === 'zh' ? '策略' : 'Strategy'}</th>
              <th>{t('l5_female_male')}</th>
              <th>{t('l5_outsider_local')}</th>
              <th>{t('l5_young_core')}</th>
            </tr>
          </thead>
          <tbody>
            {versions.map(v => {
              const g = l5.di_by_group[v];
              if (!g) return null;
              const diCell = (val: number) => (
                <td style={{ color: val < 0.80 ? 'var(--red)' : val < 0.85 ? 'var(--amber)' : 'var(--green)', fontWeight: 600 }}>
                  {val.toFixed(2)}
                  {val < 0.80 && ' ⚠'}
                </td>
              );
              return (
                <tr key={v}>
                  <td style={{ fontWeight: 600 }}>{v}</td>
                  {diCell(g.female_male)}
                  {diCell(g.outsider_local)}
                  {diCell(g.young_core)}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* AI Panel */}
      {showAi && (
        <AiPanel
          layer="l5"
          layerLabel={t('layer_l5')}
          runId={result.run_id}
          language={language}
          state={ai.state}
          onRerun={rerunAI}
          onClose={() => { ai.close(); setShowAi(false); }}
        />
      )}
    </div>
  );
}
