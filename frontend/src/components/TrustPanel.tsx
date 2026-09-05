import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RunResult, GuardrailReport, ReplicationReport, RepairResult, EvidenceBundle } from '../types';
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
  const [fix, setFix] = useState<RepairResult | null>(null);
  const [fixBusy, setFixBusy] = useState<string | null>(null);
  const [fixErr, setFixErr] = useState<string | null>(null);
  const [bundleBusy, setBundleBusy] = useState(false);
  const [bundleErr, setBundleErr] = useState<string | null>(null);

  useEffect(() => {
    setReport(null); setError(null); setRep(null); setRepErr(null);
    setFix(null); setFixErr(null); setBundleErr(null);
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

  async function runFix(code: string) {
    setFixBusy(code); setFixErr(null); setFix(null);
    try {
      setFix(await API.findFix(result.run_id, code));
    } catch (e) {
      setFixErr(e instanceof Error ? e.message : String(e));
    } finally {
      setFixBusy(null);
    }
  }

  async function downloadBundle() {
    setBundleBusy(true); setBundleErr(null);
    try {
      const b: EvidenceBundle = await API.getBundle(result.run_id, Boolean(rep));
      const blob = new Blob([b.markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `evidence-${result.run_id}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setBundleErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBundleBusy(false);
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
                <Finding key={`b${i}`} f={f} tone="red" label={t('trust_block')}
                         busy={fixBusy === f.code} onFix={() => runFix(f.code)} t={t} />
              ))}
              {report.warnings.map((f, i) => (
                <Finding key={`w${i}`} f={f} tone="amber" label={t('trust_warn')}
                         busy={fixBusy === f.code} onFix={() => runFix(f.code)} t={t} />
              ))}
              {!nBlock && !nWarn && <div className="text-xs muted">{t('trust_clean_detail')}</div>}
            </>
          )}
          {error && <div className="text-xs muted">{t('trust_unavailable')} — {error}</div>}

          {fixErr && <div className="text-xs" style={{ color: 'var(--red)' }}>{fixErr}</div>}
          {fix && <FixResult fix={fix} t={t} />}

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

          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--bd, #e5e7eb)',
                        display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <div className="text-xs bold">{t('bundle_title')}</div>
            <div className="text-xs muted" style={{ flex: 1, minWidth: 200 }}>
              {rep ? t('bundle_sub_with_rep') : t('bundle_sub_no_rep')}
            </div>
            <button className="btn sm" type="button" disabled={bundleBusy} onClick={downloadBundle}>
              {bundleBusy ? t('bundle_building') : t('bundle_download')}
            </button>
          </div>
          {bundleErr && <div className="text-xs" style={{ color: 'var(--red)', marginTop: 6 }}>{bundleErr}</div>}
        </div>
      )}
    </div>
  );
}

function Finding({ f, tone, label, busy, onFix, t }: {
  f: { code: string; detail: string };
  tone: string; label: string; busy: boolean;
  onFix: () => void; t: (k: string) => string;
}) {
  // Only findings with a knob to turn get a repair button; offering one for
  // "protected attribute used as input" would promise a fix that cannot exist.
  const repairable = ['disparate_impact', 'bad_rate_ceiling', 'approved_book_too_small'];
  return (
    <div className="text-xs" style={{ display: 'flex', gap: 8, marginBottom: 6, alignItems: 'flex-start' }}>
      <span className={`tag ${tone}`} style={{ flexShrink: 0 }}>{label}</span>
      <span style={{ flex: 1 }}><code>{f.code}</code> · {f.detail}</span>
      {repairable.includes(f.code) && (
        <button className="btn sm" type="button" disabled={busy} onClick={onFix} style={{ flexShrink: 0 }}>
          {busy ? t('fix_searching') : t('fix_button')}
        </button>
      )}
    </div>
  );
}

function FixResult({ fix, t }: { fix: RepairResult; t: (k: string) => string }) {
  return (
    <div style={{ marginTop: 10, padding: 10, borderRadius: 4, background: 'var(--bg-2, #f8f9fa)' }}>
      <div className="text-xs bold" style={{ marginBottom: 4 }}>
        {t('fix_result')} · <code>{fix.knob}</code> {t('fix_from')} {(fix.from * 100).toFixed(1)}%
      </div>
      <div className="text-xs" style={{ marginBottom: 8, color: fix.fixed ? 'var(--green)' : 'var(--amber)' }}>
        {fix.note}
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>{t('fix_value')}</th><th>{t('fix_cleared')}</th>
            <th>{t('trust_rep_apr')}</th><th>{t('trust_rep_bad')}</th><th>run</th>
          </tr>
        </thead>
        <tbody>
          {fix.attempts.map(a => (
            <tr key={a.value} style={a === fix.fixed ? { fontWeight: 600 } : undefined}>
              <td className="num">{(a.value * 100).toFixed(1)}%</td>
              <td>{a.cleared ? (a.introduced.length ? t('fix_but_new') : '✓') : '—'}</td>
              <td className="num">{a.metrics?.approval_rate != null ? (a.metrics.approval_rate * 100).toFixed(1) + '%' : '—'}</td>
              <td className="num">{a.metrics?.bad_rate != null ? (a.metrics.bad_rate * 100).toFixed(2) + '%' : '—'}</td>
              <td><code style={{ fontSize: 10 }}>{a.run_id}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
      {fix.diagnosis?.by_reason && (
        <div style={{ marginTop: 8 }}>
          <div className="text-xs bold" style={{ marginBottom: 4 }}>{t('fix_diagnosis')}</div>
          <table className="data-table">
            <thead>
              <tr><th>{t('swap_attr_rule')}</th><th>{t('fix_group')}</th><th>{t('fix_reference')}</th><th>{t('fix_gap')}</th></tr>
            </thead>
            <tbody>
              {fix.diagnosis.by_reason.filter(r => Math.abs(r.gap_pp) > 1).map(r => (
                <tr key={r.reason}>
                  <td>{r.reason}</td>
                  <td className="num">{(r.group_pct * 100).toFixed(1)}%</td>
                  <td className="num">{(r.reference_pct * 100).toFixed(1)}%</td>
                  <td className="num" style={{ color: r.gap_pp > 0 ? 'var(--red)' : undefined }}>
                    {r.gap_pp > 0 ? '+' : ''}{r.gap_pp.toFixed(1)}pp
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
