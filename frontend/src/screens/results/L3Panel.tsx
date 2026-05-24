import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, Language } from '../../types';
import { useAI } from '../../hooks/useAI';
import KpiCard from '../../components/KpiCard';
import AiPanel from '../../components/AiPanel';
import { VintageLineChart, FpdBarChart, RollRateChart } from '../../components/Chart';
import Icon from '../../components/Icon';
import API from '../../api/client';

interface L3PanelProps {
  result: RunResult;
  language: Language;
}

export default function L3Panel({ result, language }: L3PanelProps) {
  const { t } = useTranslation();
  const ai = useAI();
  const [showAi, setShowAi] = useState(false);

  const l3 = result.layers.l3;
  const challenger = l3.kpis.find(k => k.version === result.challenger);
  const champion = l3.kpis.find(k => k.version === result.champion);
  const others = l3.kpis.filter(k => k.version !== result.challenger);

  const versions = [result.challenger, result.champion, ...(result.beta ? [result.beta] : [])];

  function triggerAI() {
    setShowAi(true);
    ai.trigger((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l3', language, onThink, onResult, onDone, onErr)
    );
  }

  function rerunAI() {
    ai.rerun((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l3', language, onThink, onResult, onDone, onErr)
    );
  }

  return (
    <div className="layer-panel">
      <div className="layer-panel-header">
        <h3 className="layer-panel-title">{t('layer_l3_full')}</h3>
        <p className="layer-panel-desc">{t('l3_desc')}</p>
        {!showAi && (
          <button className="btn-ai-trigger" onClick={triggerAI} type="button">
            <Icon name="sparkles" size={15} />
            {t('ai_trigger')}
            <span className="ai-badge">{t('ai_badge')}</span>
          </button>
        )}
      </div>

      {showAi && (
        <AiPanel
          layer="l3"
          layerLabel={t('layer_l3')}
          runId={result.run_id}
          language={language}
          state={ai.state}
          onRerun={rerunAI}
          onClose={() => { ai.close(); setShowAi(false); }}
        />
      )}

      {/* KPI Cards */}
      <div className="kpi-grid">
        <KpiCard
          label={t('kpi_m12_bad')}
          value={`${((challenger?.m12_bad ?? 0) * 100).toFixed(1)}%`}
          delta={challenger && champion ? challenger.m12_bad - champion.m12_bad : undefined}
          higherIsBetter={false}
          highlight
          compareRows={others.map(k => ({ version: k.version, value: `${(k.m12_bad * 100).toFixed(1)}%` }))}
        />
        <KpiCard
          label={t('kpi_m1_m2_roll')}
          value={`${((challenger?.m1_m2_roll ?? 0) * 100).toFixed(1)}%`}
          delta={challenger && champion ? challenger.m1_m2_roll - champion.m1_m2_roll : undefined}
          higherIsBetter={false}
          compareRows={others.map(k => ({ version: k.version, value: `${(k.m1_m2_roll * 100).toFixed(1)}%` }))}
        />
        <KpiCard
          label={t('kpi_fpd')}
          value={`${((challenger?.fpd ?? 0) * 100).toFixed(1)}%`}
          delta={challenger && champion ? challenger.fpd - champion.fpd : undefined}
          higherIsBetter={false}
          compareRows={others.map(k => ({ version: k.version, value: `${(k.fpd * 100).toFixed(1)}%` }))}
        />
      </div>

      {/* Charts */}
      <div className="chart-grid chart-grid-2">
        <div className="chart-card">
          <div className="chart-title">{t('chart_vintage_title')}</div>
          <VintageLineChart data={l3.vintage} versions={versions} />
        </div>
        <div className="chart-card">
          <div className="chart-title">{t('chart_fpd_title')}</div>
          <FpdBarChart data={l3.fpd_trend} versions={versions} />
        </div>
      </div>

      <div className="chart-card">
        <div className="chart-title">{t('chart_roll_rate_title')}</div>
        <RollRateChart
          data={Object.fromEntries(versions.filter(v => l3.roll_rates[v]).map(v => [v, l3.roll_rates[v]]))}
        />
      </div>

    </div>
  );
}
