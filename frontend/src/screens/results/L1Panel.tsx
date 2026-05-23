import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, Language } from '../../types';
import { useAI } from '../../hooks/useAI';
import KpiCard from '../../components/KpiCard';
import AiPanel from '../../components/AiPanel';
import { RocChart, PsiBarChart, CalibrationChart, CsiBarChart } from '../../components/Chart';
import Icon from '../../components/Icon';
import API from '../../api/client';

interface L1PanelProps {
  result: RunResult;
  language: Language;
}

export default function L1Panel({ result, language }: L1PanelProps) {
  const { t } = useTranslation();
  const ai = useAI();
  const [showAi, setShowAi] = useState(false);

  const l1 = result.layers.l1;
  const challenger = l1.kpis.find(k => k.version === result.challenger);
  const champion = l1.kpis.find(k => k.version === result.champion);
  const others = l1.kpis.filter(k => k.version !== result.challenger);

  const latestPsi = l1.psi_monthly[l1.psi_monthly.length - 1]?.psi ?? 0;

  const versions = [result.challenger, result.champion, ...(result.beta ? [result.beta] : [])];
  const aucs: Record<string, number> = {};
  l1.kpis.forEach(k => { aucs[k.version] = k.auc; });

  function triggerAI() {
    setShowAi(true);
    ai.trigger((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l1', language, onThink, onResult, onDone, onErr)
    );
  }

  function rerunAI() {
    ai.rerun((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l1', language, onThink, onResult, onDone, onErr)
    );
  }

  return (
    <div className="layer-panel">
      <div className="layer-panel-header">
        <h3 className="layer-panel-title">{t('layer_l1_full')}</h3>
        <p className="layer-panel-desc">{t('l1_desc')}</p>
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
          label={t('kpi_ks')}
          value={challenger?.ks.toFixed(2) ?? '-'}
          delta={challenger && champion ? challenger.ks - champion.ks : undefined}
          higherIsBetter={true}
          highlight
          compareRows={others.map(k => ({ version: k.version, value: k.ks.toFixed(2) }))}
        />
        <KpiCard
          label={t('kpi_auc')}
          value={challenger?.auc.toFixed(2) ?? '-'}
          delta={challenger && champion ? challenger.auc - champion.auc : undefined}
          higherIsBetter={true}
          compareRows={others.map(k => ({ version: k.version, value: k.auc.toFixed(2) }))}
        />
        <KpiCard
          label={t('kpi_lift20')}
          value={challenger?.lift20.toFixed(1) ?? '-'}
          unit="x"
          delta={challenger && champion ? challenger.lift20 - champion.lift20 : undefined}
          higherIsBetter={true}
          compareRows={others.map(k => ({ version: k.version, value: k.lift20.toFixed(1) + 'x' }))}
        />
        <KpiCard
          label={t('kpi_brier')}
          value={challenger?.brier.toFixed(3) ?? '-'}
          delta={challenger && champion ? challenger.brier - champion.brier : undefined}
          higherIsBetter={false}
          compareRows={others.map(k => ({ version: k.version, value: k.brier.toFixed(3) }))}
        />
        <KpiCard
          label={t('kpi_psi')}
          value={latestPsi.toFixed(2)}
          higherIsBetter={false}
          delta={latestPsi - 0.10}
        />
      </div>

      {/* Charts */}
      <div className="chart-grid chart-grid-2">
        <div className="chart-card">
          <div className="chart-title">{t('chart_roc_title')}</div>
          <RocChart
            roc={Object.fromEntries(versions.filter(v => l1.roc[v]).map(v => [v, l1.roc[v]]))}
            aucs={aucs}
          />
        </div>
        <div className="chart-card">
          <div className="chart-title">{t('chart_psi_title')}</div>
          <PsiBarChart data={l1.psi_monthly} />
        </div>
      </div>

      <div className="chart-grid chart-grid-2">
        <div className="chart-card">
          <div className="chart-title">{t('chart_calibration_title')}</div>
          <CalibrationChart
            calibration={Object.fromEntries(versions.filter(v => l1.calibration[v]).map(v => [v, l1.calibration[v]]))}
          />
        </div>
        <div className="chart-card">
          <div className="chart-title">{t('chart_csi_title')}</div>
          <CsiBarChart data={l1.csi} />
        </div>
      </div>

      {/* AI Panel */}
      {showAi && (
        <AiPanel
          layer="l1"
          layerLabel={t('layer_l1')}
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
