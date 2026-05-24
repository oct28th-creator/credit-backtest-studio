import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, Language } from '../../types';
import { useAI } from '../../hooks/useAI';
import KpiCard from '../../components/KpiCard';
import AiPanel from '../../components/AiPanel';
import { FrontierChart, RarocBandChart, RejectionChart } from '../../components/Chart';
import Icon from '../../components/Icon';
import API from '../../api/client';

interface L2PanelProps {
  result: RunResult;
  language: Language;
}

export default function L2Panel({ result, language }: L2PanelProps) {
  const { t } = useTranslation();
  const ai = useAI();
  const [showAi, setShowAi] = useState(false);
  const [rejVersion, setRejVersion] = useState(result.challenger);

  const l2 = result.layers.l2;
  const challenger = l2.kpis.find(k => k.version === result.challenger);
  const champion = l2.kpis.find(k => k.version === result.champion);
  const others = l2.kpis.filter(k => k.version !== result.challenger);

  const versions = [result.challenger, result.champion, ...(result.beta ? [result.beta] : [])];

  function triggerAI() {
    setShowAi(true);
    ai.trigger((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l2', language, onThink, onResult, onDone, onErr)
    );
  }

  function rerunAI() {
    ai.rerun((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l2', language, onThink, onResult, onDone, onErr)
    );
  }

  return (
    <div className="layer-panel">
      <div className="layer-panel-header">
        <h3 className="layer-panel-title">{t('layer_l2_full')}</h3>
        <p className="layer-panel-desc">{t('l2_desc')}</p>
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
          layer="l2"
          layerLabel={t('layer_l2')}
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
          label={t('kpi_approval_rate')}
          value={`${((challenger?.approval_rate ?? 0) * 100).toFixed(0)}%`}
          delta={challenger && champion ? challenger.approval_rate - champion.approval_rate : undefined}
          higherIsBetter={true}
          highlight
          compareRows={others.map(k => ({ version: k.version, value: `${(k.approval_rate * 100).toFixed(0)}%` }))}
        />
        <KpiCard
          label={t('kpi_avg_profit')}
          value={`¥${challenger?.avg_profit.toFixed(0) ?? '-'}`}
          delta={challenger && champion ? challenger.avg_profit - champion.avg_profit : undefined}
          higherIsBetter={true}
          compareRows={others.map(k => ({ version: k.version, value: `¥${k.avg_profit.toFixed(0)}` }))}
        />
        <KpiCard
          label={t('kpi_raroc')}
          value={`${((challenger?.raroc ?? 0) * 100).toFixed(0)}%`}
          delta={challenger && champion ? challenger.raroc - champion.raroc : undefined}
          higherIsBetter={true}
          compareRows={others.map(k => ({ version: k.version, value: `${(k.raroc * 100).toFixed(0)}%` }))}
        />
        <KpiCard
          label={t('kpi_el')}
          value={`${((challenger?.el ?? 0) * 100).toFixed(1)}%`}
          delta={challenger && champion ? challenger.el - champion.el : undefined}
          higherIsBetter={false}
          compareRows={others.map(k => ({ version: k.version, value: `${(k.el * 100).toFixed(1)}%` }))}
        />
      </div>

      {/* Charts */}
      <div className="chart-grid chart-grid-2">
        <div className="chart-card">
          <div className="chart-title">{t('chart_frontier_title')}</div>
          <FrontierChart data={l2.frontier} />
        </div>
        <div className="chart-card">
          <div className="chart-title">{t('chart_raroc_band_title')}</div>
          <RarocBandChart
            data={Object.fromEntries(versions.filter(v => l2.raroc_bands[v]).map(v => [v, l2.raroc_bands[v]]))}
          />
        </div>
      </div>

      <div className="chart-card">
        <div className="chart-title-row">
          <div className="chart-title">{t('chart_rejection_title')}</div>
          <div className="version-tabs">
            {versions.map(v => (
              <button
                key={v}
                className={`version-tab ${rejVersion === v ? 'version-tab-active' : ''}`}
                onClick={() => setRejVersion(v)}
                type="button"
              >
                {v}
              </button>
            ))}
          </div>
        </div>
        <RejectionChart data={l2.rejection_reasons} selectedVersion={rejVersion} />
      </div>

    </div>
  );
}
