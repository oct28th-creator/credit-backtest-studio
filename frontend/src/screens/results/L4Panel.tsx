import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, SwapMatrix, Language } from '../../types';
import { useAI } from '../../hooks/useAI';
import AiPanel from '../../components/AiPanel';
import Icon from '../../components/Icon';
import API from '../../api/client';

interface L4PanelProps {
  result: RunResult;
  language: Language;
}

function pct(n: number) { return `${(n * 100).toFixed(1)}%`; }
function num(n: number) { return n.toLocaleString(); }

export default function L4Panel({ result, language }: L4PanelProps) {
  const { t } = useTranslation();
  const ai = useAI();
  const [showAi, setShowAi] = useState(false);

  const l4 = result.layers.l4;
  const matrixKeys = Object.keys(l4.matrices);
  const [selectedKey, setSelectedKey] = useState(matrixKeys[0] ?? '');

  const matrix: SwapMatrix | undefined = l4.matrices[selectedKey];

  function triggerAI() {
    setShowAi(true);
    ai.trigger((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l4', language, onThink, onResult, onDone, onErr)
    );
  }

  function rerunAI() {
    ai.rerun((onThink, onResult, onDone, onErr) =>
      API.streamAnalyzeLayer(result.run_id, 'l4', language, onThink, onResult, onDone, onErr)
    );
  }

  const keyLabel = (k: string) => {
    const [a, , b] = k.split('_vs_');
    return `${a} vs ${b}`;
  };

  return (
    <div className="layer-panel">
      <div className="layer-panel-header">
        <h3 className="layer-panel-title">{t('layer_l4_full')}</h3>
        <p className="layer-panel-desc">{t('l4_desc')}</p>
        {!showAi && (
          <button className="btn-ai-trigger" onClick={triggerAI} type="button">
            <Icon name="sparkles" size={15} />
            {t('ai_trigger')}
            <span className="ai-badge">{t('ai_badge')}</span>
          </button>
        )}
      </div>

      {/* Matrix Selector */}
      {matrixKeys.length > 1 && (
        <div className="version-tabs" style={{ marginBottom: 16 }}>
          {matrixKeys.map(k => (
            <button
              key={k}
              className={`version-tab ${selectedKey === k ? 'version-tab-active' : ''}`}
              onClick={() => setSelectedKey(k)}
              type="button"
            >
              <Icon name="swap" size={13} />
              {t('swap_compare')} {keyLabel(k)}
            </button>
          ))}
        </div>
      )}

      {matrix && (
        <>
          {/* Consistency KPIs */}
          <div className="swap-kpi-row">
            <div className="swap-kpi-item">
              <span className="swap-kpi-label">{t('kpi_consistency')}</span>
              <span className="swap-kpi-value">{pct(matrix.consistency)}</span>
            </div>
            <div className="swap-kpi-sep" />
            <div className="swap-kpi-item">
              <span className="swap-kpi-label">{t('kpi_p_value')}</span>
              <span className={`swap-kpi-value ${matrix.p_value < 0.05 ? 'swap-kpi-sig' : ''}`}>
                {matrix.p_value.toFixed(3)}
                {matrix.p_value < 0.05 && <Icon name="warn" size={13} style={{ marginLeft: 4, color: 'var(--amber)' }} />}
              </span>
            </div>
            <div className="swap-kpi-sep" />
            <div className="swap-kpi-item">
              <span className="swap-kpi-label">{t('swap_base_bad_rate')}</span>
              <span className="swap-kpi-value">{pct(matrix.base_bad_rate)}</span>
            </div>
            <div className="swap-kpi-sep" />
            <div className="swap-kpi-item">
              <span className="swap-kpi-label">{t('swap_swap_out_lift')}</span>
              <span className="swap-kpi-value">{matrix.swap_out_lift.toFixed(2)}x</span>
            </div>
          </div>

          {/* 4-quadrant matrix */}
          <div className="swap-matrix-grid">
            {/* Header row */}
            <div className="swap-matrix-corner" />
            <div className="swap-matrix-col-header swap-champ-approve">{t('swap_champion_approve')}</div>
            <div className="swap-matrix-col-header swap-champ-reject">{t('swap_champion_reject')}</div>

            {/* Row 1: Challenger Approve */}
            <div className="swap-matrix-row-header swap-chal-approve">{t('swap_challenger_approve')}</div>
            <div className="swap-quadrant swap-double-approve">
              <div className="swap-quad-label">{t('swap_double_approve')}</div>
              <div className="swap-quad-count">{num(matrix.double_approve.count)}</div>
              <div className="swap-quad-rate">{t('swap_bad_rate')}: {pct(matrix.double_approve.bad_rate)}</div>
            </div>
            <div className="swap-quadrant swap-swap-in">
              <div className="swap-quad-label">{t('swap_in')}</div>
              <div className="swap-quad-count">{num(matrix.swap_in.count)}</div>
              <div className="swap-quad-rate">{t('swap_bad_rate')}: {pct(matrix.swap_in.bad_rate)}</div>
            </div>

            {/* Row 2: Challenger Reject */}
            <div className="swap-matrix-row-header swap-chal-reject">{t('swap_challenger_reject')}</div>
            <div className="swap-quadrant swap-swap-out">
              <div className="swap-quad-label">{t('swap_out')}</div>
              <div className="swap-quad-count">{num(matrix.swap_out.count)}</div>
              <div className="swap-quad-rate">{t('swap_bad_rate')}: {pct(matrix.swap_out.bad_rate)}</div>
            </div>
            <div className="swap-quadrant swap-double-reject">
              <div className="swap-quad-label">{t('swap_double_reject')}</div>
              <div className="swap-quad-count">{num(matrix.double_reject.count)}</div>
            </div>
          </div>

          {/* Consistency by band table */}
          <div className="chart-card" style={{ marginTop: 20 }}>
            <div className="chart-title">{t('swap_consistency_by_band')}</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('chart_score_band')}</th>
                  <th>{t('chart_consistency')}</th>
                </tr>
              </thead>
              <tbody>
                {matrix.consistency_by_band.map(row => (
                  <tr key={row.band}>
                    <td>{row.band}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div
                          style={{
                            width: `${row.consistency * 100}px`,
                            maxWidth: 200,
                            height: 8,
                            borderRadius: 4,
                            background: row.consistency >= 0.95 ? 'var(--green)' : row.consistency >= 0.90 ? 'var(--amber)' : 'var(--red)',
                          }}
                        />
                        {pct(row.consistency)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* AI Panel */}
      {showAi && (
        <AiPanel
          layer="l4"
          layerLabel={t('layer_l4')}
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
