import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, GainDecomposition as Decomposition } from '../types';
import API from '../api/client';

/**
 * Where the challenger's extra approvals came from.
 *
 * "Approves twice as many at the same bad rate" is the headline everyone
 * reads off L2. It is not a conclusion until you know whether the extra
 * accounts were won by a sharper model or by a loosened gate — those go down
 * different approval paths, and only one of them is a model release.
 *
 * The split is computed from the swap-in attribution, so the sentence above
 * the quadrants is arithmetic, not narration.
 */
export default function GainDecompositionCard({ result, strategy }: { result: RunResult; strategy: string }) {
  const { t } = useTranslation();
  const [dec, setDec] = useState<Decomposition | null>(null);

  useEffect(() => {
    setDec(null);
    if (result.demo) return;
    API.getDecomposition(result.run_id).then(setDec).catch(() => setDec(null));
  }, [result.run_id, result.demo, strategy]);

  if (!dec) return null;
  const tone = dec.driver === 'model' ? 'green' : dec.driver === 'policy' ? 'amber' : 'blue';

  return (
    <div className="chart-card" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div className="chart-title" style={{ margin: 0 }}>{t('gain_title')}</div>
        <span className={`tag ${tone}`}>{t(`gain_driver_${dec.driver}`)}</span>
      </div>

      <div className="text-sm" style={{ marginBottom: 12, lineHeight: 1.7 }}>{dec.headline}</div>

      <div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', marginBottom: 6 }}>
        <div style={{ width: `${dec.model_driven.share * 100}%`, background: 'var(--green)' }} />
        <div style={{ width: `${dec.policy_driven.share * 100}%`, background: 'var(--amber)' }} />
      </div>
      <div className="text-xs muted" style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
        <span><span style={{ color: 'var(--green)' }}>■</span> {t('gain_model')} {(dec.model_driven.share * 100).toFixed(0)}% · {dec.model_driven.n.toLocaleString()} {t('swap_attr_n')}</span>
        <span><span style={{ color: 'var(--amber)' }}>■</span> {t('gain_policy')} {(dec.policy_driven.share * 100).toFixed(0)}% · {dec.policy_driven.n.toLocaleString()} {t('swap_attr_n')}</span>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>{t('gain_source')}</th><th>{t('swap_attr_rule')}</th>
            <th>{t('swap_attr_n')}</th><th>{t('swap_attr_bad')}</th>
          </tr>
        </thead>
        <tbody>
          {dec.model_driven.rules.map(r => (
            <tr key={`m-${r.reason}`}>
              <td><span className="tag green">{t('gain_model')}</span></td>
              <td>{r.reason}<div className="text-xs muted" style={{ fontFamily: 'var(--mono)' }}>{r.rule}</div></td>
              <td className="num">{r.n.toLocaleString()}</td>
              <td className="num">{(r.bad_rate * 100).toFixed(2)}%</td>
            </tr>
          ))}
          {dec.policy_driven.rules.map(r => (
            <tr key={`p-${r.reason}`}>
              <td><span className="tag amber">{t('gain_policy')}</span></td>
              <td>{r.reason}<div className="text-xs muted" style={{ fontFamily: 'var(--mono)' }}>{r.rule}</div></td>
              <td className="num">{r.n.toLocaleString()}</td>
              <td className="num">{(r.bad_rate * 100).toFixed(2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
