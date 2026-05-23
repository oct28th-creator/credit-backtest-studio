import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, Language, Strategy } from '../types';
import Icon from '../components/Icon';

interface StrategyAnalysisScreenProps {
  result: RunResult;
  strategies: Strategy[];
  language: Language;
}

type SubTab = 'overview' | 'anti_fraud' | 'if_else' | 'decision_table' | 'cross_decision' | 'scorecard' | 'bifurcation';

const SUB_TABS: Array<{ key: SubTab; labelKey: string; icon: string }> = [
  { key: 'overview', labelKey: 'strategy_overview', icon: '总览' },
  { key: 'anti_fraud', labelKey: 'strategy_anti_fraud', icon: '🛡' },
  { key: 'if_else', labelKey: 'strategy_if_else', icon: '📋' },
  { key: 'decision_table', labelKey: 'strategy_decision_table', icon: '📑' },
  { key: 'cross_decision', labelKey: 'strategy_cross_decision', icon: '🔀' },
  { key: 'scorecard', labelKey: 'strategy_scorecard', icon: '📊' },
  { key: 'bifurcation', labelKey: 'strategy_bifurcation', icon: '🌳' },
];

export default function StrategyAnalysisScreen({ result, strategies, language }: StrategyAnalysisScreenProps) {
  const { t } = useTranslation();
  const [subTab, setSubTab] = useState<SubTab>('overview');

  const versions = [result.challenger, result.champion, ...(result.beta ? [result.beta] : [])];
  const strats = versions.map(v => strategies.find(s => s.id === v)).filter(Boolean) as Strategy[];

  // Pipeline steps
  const PIPELINE = [
    t('strategy_anti_fraud'),
    'IF-ELSE',
    t('strategy_decision_table'),
    t('strategy_cross_decision'),
    t('strategy_scorecard'),
    t('strategy_bifurcation'),
  ];

  return (
    <div className="strategy-analysis">
      {/* Decision Pipeline */}
      <div className="pipeline-bar">
        <span className="pipeline-label">{t('strategy_pipeline')}:</span>
        {PIPELINE.map((step, i) => (
          <React.Fragment key={step}>
            <span className="pipeline-step">{step}</span>
            {i < PIPELINE.length - 1 && (
              <Icon name="chev_right" size={14} style={{ color: 'var(--ink-4)' }} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Sub-tabs */}
      <div className="subtabs">
        {SUB_TABS.map(tab => (
          <button
            key={tab.key}
            className={`subtab ${subTab === tab.key ? 'subtab-active' : ''}`}
            onClick={() => setSubTab(tab.key)}
            type="button"
          >
            <span>{tab.icon}</span>
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {subTab === 'overview' && (
        <div className="strategy-table-wrap">
          <table className="data-table strategy-compare-table">
            <thead>
              <tr>
                <th>{language === 'zh' ? '参数' : 'Parameter'}</th>
                {strats.map(s => <th key={s.id}>{s.id}</th>)}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{t('strategy_dti_limit')}</td>
                {strats.map(s => <td key={s.id}>{(s.dti_limit * 100).toFixed(0)}%</td>)}
              </tr>
              <tr>
                <td>{t('strategy_score_cutoff')}</td>
                {strats.map(s => <td key={s.id}>{s.score_cutoff ?? '-'}</td>)}
              </tr>
              <tr>
                <td>{t('strategy_limit_increase_min')}</td>
                {strats.map(s => <td key={s.id}>¥{s.limit_increase_min.toLocaleString()}</td>)}
              </tr>
              <tr>
                <td>{t('strategy_limit_increase_max')}</td>
                {strats.map(s => <td key={s.id}>¥{s.limit_increase_max.toLocaleString()}</td>)}
              </tr>
              <tr>
                <td>{t('strategy_mob_months')}</td>
                {strats.map(s => <td key={s.id}>{s.mob_months}</td>)}
              </tr>
              <tr>
                <td>{t('strategy_online_since')}</td>
                {strats.map(s => <td key={s.id}>{s.online_since ?? '-'}</td>)}
              </tr>
              <tr>
                <td>{language === 'zh' ? '反欺诈版本' : 'Anti-fraud Version'}</td>
                {strats.map(s => <td key={s.id}>{s.anti_fraud}</td>)}
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Anti-fraud Tab */}
      {subTab === 'anti_fraud' && (
        <div className="strategy-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('strategy_rule')}</th>
                <th>{t('strategy_description')}</th>
                {strats.map(s => <th key={s.id}>{s.id}</th>)}
              </tr>
            </thead>
            <tbody>
              {Array.from(new Set(strats.flatMap(s => s.rules.anti_fraud_rules.map(r => r.rule)))).map(rule => {
                const desc = strats.flatMap(s => s.rules.anti_fraud_rules).find(r => r.rule === rule);
                return (
                  <tr key={rule}>
                    <td><code>{rule}</code></td>
                    <td>{language === 'zh' ? desc?.desc_zh : desc?.desc_en}</td>
                    {strats.map(s => (
                      <td key={s.id}>
                        {s.rules.anti_fraud_rules.some(r => r.rule === rule)
                          ? <Icon name="check" size={14} style={{ color: 'var(--green)' }} />
                          : <Icon name="x" size={14} style={{ color: 'var(--ink-5)' }} />}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* IF-ELSE Tab */}
      {subTab === 'if_else' && (
        <div className="strategy-table-wrap">
          {strats.map(s => (
            <div key={s.id} style={{ marginBottom: 24 }}>
              <div className="chart-title">{s.id} — IF-ELSE</div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('strategy_condition')}</th>
                    <th>{t('strategy_action')}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.rules.if_else.map((rule, i) => (
                    <tr key={i}>
                      <td><code>{rule.condition}</code></td>
                      <td>{language === 'zh' ? rule.action_zh : rule.action_en}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {/* Decision Table Tab */}
      {subTab === 'decision_table' && (
        <div className="strategy-table-wrap">
          {strats.map(s => (
            <div key={s.id} style={{ marginBottom: 24 }}>
              <div className="chart-title">{s.id} — {t('strategy_decision_table')}</div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('strategy_dti_band')}</th>
                    <th>{t('strategy_score_band_col')}</th>
                    <th>{t('strategy_action')}</th>
                    <th>{t('strategy_rate')}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.rules.decision_table.map((row, i) => (
                    <tr key={i}>
                      <td>{row.dti_band}</td>
                      <td>{row.score_band}</td>
                      <td>{language === 'zh' ? row.action_zh : row.action_en}</td>
                      <td>{row.rate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {/* Cross Decision Table Tab */}
      {subTab === 'cross_decision' && (
        <div className="strategy-table-wrap">
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--ink-4)' }}>
            <Icon name="swap" size={32} style={{ marginBottom: 8 }} />
            <div>{language === 'zh' ? '交叉决策表由 L4 换客群矩阵提供' : 'Cross decision table is provided by the L4 Swap-Set Matrix'}</div>
          </div>
        </div>
      )}

      {/* Scorecard Tab */}
      {subTab === 'scorecard' && (
        <div className="strategy-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('strategy_feature')}</th>
                {strats.map(s => (
                  <React.Fragment key={s.id}>
                    <th>{s.id} {t('strategy_weight')}</th>
                    <th>{s.id} {t('strategy_direction')}</th>
                  </React.Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from(new Set(strats.flatMap(s => s.rules.scorecard_features.map(f => f.feature)))).map(feat => (
                <tr key={feat}>
                  <td>{feat}</td>
                  {strats.map(s => {
                    const f = s.rules.scorecard_features.find(sf => sf.feature === feat);
                    return (
                      <React.Fragment key={s.id}>
                        <td>{f ? f.weight.toFixed(2) : '-'}</td>
                        <td style={{ color: f?.direction === 'positive' ? 'var(--green)' : 'var(--red)' }}>
                          {f ? (f.direction === 'positive' ? t('strategy_positive') : t('strategy_negative')) : '-'}
                        </td>
                      </React.Fragment>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Bifurcation Tab */}
      {subTab === 'bifurcation' && (
        <div className="strategy-table-wrap">
          {strats.map(s => (
            <div key={s.id} style={{ marginBottom: 24 }}>
              <div className="chart-title">{s.id} — {t('strategy_bifurcation')}</div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('strategy_branch')}</th>
                    <th>{t('strategy_pct')}</th>
                    <th>{t('kpi_m12_bad')}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.rules.bifurcation.map((b, i) => (
                    <tr key={i}>
                      <td>{language === 'zh' ? b.branch_zh : b.branch_en}</td>
                      <td>{(b.pct * 100).toFixed(0)}%</td>
                      <td>{b.bad_rate !== null ? `${(b.bad_rate * 100).toFixed(1)}%` : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
