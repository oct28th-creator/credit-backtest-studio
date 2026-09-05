import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunEnvironment } from '../types';

/**
 * The world this run assumed, shown next to its numbers.
 *
 * Two things the platform used to leave implicit and now states outright:
 * what the environment may NOT be used to claim, and — under reject
 * inference — how far the estimation method is from the truth it could not
 * see. A conclusion whose method errs by more than the effect it reports is
 * flagged here, not buried in an appendix.
 */
export default function EnvPanel({ env }: { env?: RunEnvironment }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  if (!env) return null;

  const ri = env.reject_inference;
  const err = ri?.max_relative_error ?? null;
  const tone = err === null ? 'blue' : err > 0.5 ? 'red' : err > 0.25 ? 'amber' : 'green';
  const confTone = env.confidence === 'high' ? 'green' : env.confidence === 'medium' ? 'amber' : 'red';

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div
        className="card-hd"
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
        onClick={() => setOpen(o => !o)}
      >
        <div className="card-title">{t('env_title')}</div>
        <span className="tag blue">{env.level} · {env.name_zh}</span>
        <span className={`tag ${confTone}`}>{t('env_confidence')}: {t(`env_conf_${env.confidence}`)}</span>
        {err !== null && (
          <span className={`tag ${tone}`}>
            {t('env_ri_error')}: {(err * 100).toFixed(0)}%
          </span>
        )}
        <span className="text-xs muted" style={{ marginLeft: 'auto' }}>
          {open ? t('env_collapse') : t('env_expand')}
        </span>
      </div>

      {open && (
        <div className="card-body">
          <div className="text-xs bold" style={{ marginBottom: 4 }}>{t('env_not_valid_for')}</div>
          <ul className="text-xs muted" style={{ margin: '0 0 12px 16px' }}>
            {env.not_valid_for.map(x => <li key={x} style={{ marginBottom: 2 }}>{x}</li>)}
          </ul>

          {ri && (
            <>
              <div className="text-xs bold" style={{ marginBottom: 4 }}>
                {t('env_ri_title')} · {t(`cfg_ri_m_${ri.mode}`)}
              </div>
              <div className="text-xs muted" style={{ marginBottom: 8 }}>
                {t('env_ri_masked', { observed: ri.n_observed.toLocaleString(), masked: ri.n_masked.toLocaleString() })}
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="tbl text-xs" style={{ width: '100%' }}>
                  <thead>
                    <tr>
                      <th>{t('env_ri_strategy')}</th>
                      <th>{t('env_ri_n')}</th>
                      <th>{t('env_ri_estimated')}</th>
                      <th>{t('env_ri_oracle')}</th>
                      <th>{t('env_ri_bias')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ri.strategies).map(([sid, r]) => (
                      <tr key={sid}>
                        <td>{sid}</td>
                        <td className="num">{r.n_swap_in.toLocaleString()}</td>
                        <td className="num">{r.estimated_bad_rate != null ? (r.estimated_bad_rate * 100).toFixed(2) + '%' : '—'}</td>
                        <td className="num">{r.oracle_bad_rate != null ? (r.oracle_bad_rate * 100).toFixed(2) + '%' : '—'}</td>
                        <td className="num" style={{ color: (r.bias_pp ?? 0) > 0 ? 'var(--red, #dc2626)' : 'var(--amber, #d97706)' }}>
                          {r.bias_pp != null ? (r.bias_pp > 0 ? '+' : '') + r.bias_pp.toFixed(2) + 'pp' : '—'}
                          {r.relative_error != null && ` (${(r.relative_error * 100).toFixed(0)}%)`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="text-xs muted" style={{ marginTop: 8 }}>{ri.note}</div>
            </>
          )}
          {env.note && <div className="text-xs muted" style={{ marginTop: 8 }}>{env.note}</div>}
        </div>
      )}
    </div>
  );
}
