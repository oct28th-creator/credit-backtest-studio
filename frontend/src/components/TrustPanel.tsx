import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, GuardrailReport, ReplicationReport } from '../types';
import API from '../api/client';

/**
 * Can this result be trusted? The same deterministic checks that bind the
 * agent's Critic, shown to the person reading the numbers — plus the one
 * question a single run can never answer (strategy difference, or sampling
 * difference?), answerable here with one click.
 */
export default function TrustPanel({ result }: { result: RunResult }) {
  const { t } = useTranslation();
  const [report, setReport] = useState<GuardrailReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rep, setRep] = useState<ReplicationReport | null>(null);
  const [repBusy, setRepBusy] = useState(false);
  const [repErr, setRepErr] = useState<string | null>(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    setReport(null); setError(null); setRep(null); setRepErr(null);
    if (result.demo) return;
    API.getGuardrails(result.run_id).then(setReport).catch(e => setError(String(e)));
  }, [result.run_id, result.demo]);

  async function runReplication() {
    setRepBusy(true); setRepErr(null);
    try {
      setRep(await API.replicate(result.config, 3));
    } catch (e) {
      setRepErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRepBusy(false);
    }
  }

  if (result.demo) return null;

  const nBlock = report?.blocking.length ?? 0;
  const nWarn = report?.warnings.length ?? 0;
  const headTone = !report ? 'blue' : nBlock ? 'red' : nWarn ? 'amber' : 'green';
  const headText = !report
    ? (error ? t('trust_unavailable') : t('trust_checking'))
    : nBlock ? t('trust_blocked', { n: nBlock })
    : nWarn ? t('trust_warned', { n: nWarn })
    : t('trust_clean');

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div
        className="card-hd"
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
        onClick={() => setOpen(o => !o)}
      >
        <div className="card-title">{t('trust_title')}</div>
        <span className={`tag ${headTone}`}>{headText}</span>
        {rep && (
          <span className={`tag ${rep.stable ? 'green' : 'red'}`}>
            {rep.stable ? t('trust_rep_stable') : t('trust_rep_unstable')}
          </span>
        )}
        <span className="text-xs muted" style={{ marginLeft: 'auto' }}>{open ? t('env_collapse') : t('env_expand')}</span>
      </div>

      {open && (
        <div className="card-body">
          {report && (
            <>
              {report.blocking.map((f, i) => (
                <div key={`b${i}`} className="text-xs" style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                  <span className="tag red" style={{ flexShrink: 0 }}>{t('trust_block')}</span>
                  <span><code>{f.code}</code> · {f.detail}</span>
                </div>
              ))}
              {report.warnings.map((f, i) => (
                <div key={`w${i}`} className="text-xs" style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                  <span className="tag amber" style={{ flexShrink: 0 }}>{t('trust_warn')}</span>
                  <span><code>{f.code}</code> · {f.detail}</span>
                </div>
              ))}
              {!nBlock && !nWarn && <div className="text-xs muted">{t('trust_clean_detail')}</div>}
            </>
          )}
          {error && <div className="text-xs muted">{t('trust_unavailable')} — {error}</div>}

          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--bd, #e5e7eb)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div className="text-xs bold">{t('trust_rep_title')}</div>
              <div className="text-xs muted" style={{ flex: 1, minWidth: 200 }}>{t('trust_rep_sub')}</div>
              <button className="btn sm" type="button" disabled={repBusy} onClick={runReplication}>
                {repBusy ? t('trust_rep_running') : t('trust_rep_button')}
              </button>
            </div>
            {repErr && <div className="text-xs" style={{ color: 'var(--red)', marginTop: 6 }}>{repErr}</div>}
            {rep && (
              <div style={{ marginTop: 10 }}>
                <div className="text-xs" style={{ marginBottom: 8 }}>{rep.verdict}</div>
                <div style={{ overflowX: 'auto' }}>
                  <table className="tbl text-xs" style={{ width: '100%' }}>
                    <thead>
                      <tr>
                        <th>{t('env_ri_strategy')}</th>
                        <th>RAROC μ</th><th>σ</th><th>95% CI</th>
                        <th>{t('trust_rep_apr')}</th><th>{t('trust_rep_bad')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(rep.strategies).map(([sid, m]) => (
                        <tr key={sid}>
                          <td>{sid}</td>
                          <td className="num">{m.raroc ? (m.raroc.mean * 100).toFixed(2) + '%' : '—'}</td>
                          <td className="num">{m.raroc ? (m.raroc.std * 100).toFixed(2) + 'pp' : '—'}</td>
                          <td className="num">{m.raroc?.ci95 ? `${(m.raroc.ci95[0] * 100).toFixed(1)}–${(m.raroc.ci95[1] * 100).toFixed(1)}%` : '—'}</td>
                          <td className="num">{m.approval_rate ? (m.approval_rate.mean * 100).toFixed(1) + '%' : '—'}</td>
                          <td className="num">{m.bad_rate ? (m.bad_rate.mean * 100).toFixed(2) + '%' : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="text-xs muted" style={{ marginTop: 6 }}>{t('trust_rep_seeds')}: {rep.seeds.join(', ')}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
