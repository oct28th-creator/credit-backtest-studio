import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { AgentEvent, ExperimentConfig, Language } from '../types';
import API from '../api/client';
import Icon from '../components/Icon';

interface AgentScreenProps {
  language: Language;
  /** Config of the run the user was last looking at, if any — the natural base. */
  baseConfig: Partial<ExperimentConfig> | null;
  onOpenRun: (runId: string) => void;
}

const DEFAULT_BASE: Partial<ExperimentConfig> = {
  champion: 'v2.2', challenger: 'v2.3', beta: null, sample_id: 'consumer_2024q1q2',
};

const PHASES = ['session', 'prior_work', 'plan', 'experiment', 'guardrails', 'comparison', 'findings', 'replication', 'critique', 'done'];

const EXAMPLES = [
  'v2.3 放宽通过率到 55% 后，RAROC 是否仍优于 v2.2？',
  '把 v2.3 的 DTI 上限从 0.68 收紧到 0.60，坏账能降多少、通过率损失多少？',
  'v2.4-Beta 在 18-25 岁客群上的公平性问题，能否通过调阈值解决？',
];

/**
 * An investigation is a first-class object: a question, a bounded plan, real
 * runs, deterministic checks, a replication, and an adversarial verdict —
 * each phase landing on screen as it happens, every run one click away.
 */
export default function AgentScreen({ language, baseConfig, onOpenRun }: AgentScreenProps) {
  const { t } = useTranslation();
  const [goal, setGoal] = useState('');
  const [budget, setBudget] = useState(6);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const base = baseConfig ?? DEFAULT_BASE;

  useEffect(() => () => abortRef.current?.(), []);

  function start(text?: string) {
    const g = (text ?? goal).trim();
    if (!g || running) return;
    setGoal(g); setEvents([]); setError(null); setRunning(true);
    abortRef.current = API.streamInvestigate(
      { goal: g, base_config: base, language, budget: { max_experiments: budget } },
      e => setEvents(prev => [...prev, e]),
      () => setRunning(false),
      err => { setError(err.message); setRunning(false); },
    );
  }

  function stop() { abortRef.current?.(); setRunning(false); }

  const byPhase = (name: string) => events.filter(e => e.phase === name);
  const last = (name: string) => byPhase(name).slice(-1)[0];
  const reached = new Set(events.map(e => e.phase));

  return (
    <div className="page">
      <div className="page-hd">
        <div>
          <div className="page-title">{t('agent_title')}</div>
          <div className="page-sub">{t('agent_sub')}</div>
        </div>
      </div>

      {/* Ask */}
      <div className="card mb16">
        <div className="card-body">
          <textarea
            className="ai-ta"
            rows={2}
            placeholder={t('agent_placeholder')}
            value={goal}
            onChange={e => setGoal(e.target.value)}
            disabled={running}
          />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0' }}>
            {EXAMPLES.map(x => (
              <button key={x} type="button" className="btn sm" disabled={running} onClick={() => start(x)}>{x}</button>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <span className="text-xs muted">
              {t('agent_base')}: <code>{base.champion}</code> vs <code>{base.challenger}</code> · {base.sample_id}
            </span>
            <label className="text-xs muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {t('agent_budget')}
              <input type="number" min={2} max={12} value={budget} disabled={running}
                     onChange={e => setBudget(Number(e.target.value))} style={{ width: 56 }} />
            </label>
            <span style={{ flex: 1 }} />
            {running
              ? <button className="btn" type="button" onClick={stop}>{t('agent_stop')}</button>
              : <button className="btn primary" type="button" onClick={() => start()}><Icon name="ai" size={12} /> {t('agent_start')}</button>}
          </div>
          {error && <div className="text-xs" style={{ color: 'var(--red)', marginTop: 8 }}>{error}</div>}
        </div>
      </div>

      {/* Phase rail */}
      {events.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
          {PHASES.map(p => (
            <span key={p} className={`tag ${reached.has(p) ? 'green' : ''}`} style={{ fontFamily: 'var(--mono)', textTransform: 'none', letterSpacing: 0 }}>
              {t(`agent_phase_${p}`)}
            </span>
          ))}
          {running && <span className="dots-spinner" />}
        </div>
      )}

      {/* Prior work */}
      {last('prior_work') && (last('prior_work') as unknown as { runs?: unknown[] }).runs && ((last('prior_work') as unknown as { runs: Array<{ run_id: string; hypothesis?: string; conclusion?: string }> }).runs.length > 0) && (
        <Section title={t('agent_sec_prior')}>
          {(last('prior_work') as unknown as { runs: Array<{ run_id: string; hypothesis?: string; conclusion?: string }> }).runs.map(r => (
            <div key={r.run_id} className="text-xs" style={{ marginBottom: 4 }}>
              <a href="#" onClick={e => { e.preventDefault(); onOpenRun(r.run_id); }}><code>{r.run_id}</code></a> · {r.hypothesis ?? ''} {r.conclusion ? `→ ${r.conclusion}` : ''}
            </div>
          ))}
        </Section>
      )}

      {/* Plan */}
      {last('plan') && (
        <Section title={t('agent_sec_plan')} tag={(last('plan') as unknown as { plan: { source: string } }).plan.source === 'llm' ? 'LLM' : t('agent_fallback')}>
          <PlanView plan={(last('plan') as unknown as { plan: Plan }).plan} t={t} />
        </Section>
      )}

      {/* Experiments */}
      {byPhase('experiment').length > 0 && (
        <Section title={`${t('agent_sec_runs')} · ${byPhase('experiment').length}`}>
          <table className="data-table">
            <thead><tr><th>{t('agent_run_label')}</th><th>run_id</th><th>{t('agent_run_cached')}</th><th>{base.challenger} {t('trust_rep_apr')}</th><th>{t('trust_rep_bad')}</th><th>RAROC</th></tr></thead>
            <tbody>
              {byPhase('experiment').map((e, i) => {
                const ev = e as unknown as ExperimentEvent;
                const chall = ev.metrics?.strategies ? Object.values(ev.metrics.strategies).find(s => s.role === 'challenger') : undefined;
                return (
                  <tr key={i}>
                    <td>{ev.label}</td>
                    <td><a href="#" onClick={x => { x.preventDefault(); onOpenRun(ev.run_id); }}><code>{ev.run_id}</code></a></td>
                    <td>{ev.cached ? t('agent_yes') : ''}</td>
                    <td className="num">{chall?.approval_rate != null ? (chall.approval_rate * 100).toFixed(1) + '%' : '—'}</td>
                    <td className="num">{chall?.bad_rate != null ? (chall.bad_rate * 100).toFixed(2) + '%' : '—'}</td>
                    <td className="num">{chall?.raroc != null ? (chall.raroc * 100).toFixed(1) + '%' : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {byPhase('experiment_failed').map((e, i) => (
            <div key={i} className="text-xs" style={{ color: 'var(--red)', marginTop: 6 }}>{String(e.label)}: {String(e.error)}</div>
          ))}
          {last('budget_stop') && <div className="text-xs" style={{ color: 'var(--amber)', marginTop: 6 }}>{String(last('budget_stop')!.detail)}</div>}
        </Section>
      )}

      {/* Guardrails */}
      {last('guardrails') && (
        <Section title={t('agent_sec_guardrails')} tag={(last('guardrails') as unknown as { report: Report }).report.ok ? t('trust_clean') : t('trust_block')}
                 tone={(last('guardrails') as unknown as { report: Report }).report.ok ? 'green' : 'red'}>
          {((last('guardrails') as unknown as { report: Report }).report.blocking).map((b, i) => (
            <div key={`b${i}`} className="text-xs" style={{ marginBottom: 4 }}><span className="tag red">{t('trust_block')}</span> {b.detail}</div>
          ))}
          {((last('guardrails') as unknown as { report: Report }).report.warnings).slice(0, 6).map((w, i) => (
            <div key={`w${i}`} className="text-xs" style={{ marginBottom: 4 }}><span className="tag amber">{t('trust_warn')}</span> {w.detail}</div>
          ))}
        </Section>
      )}

      {/* Findings */}
      {last('findings') && (
        <Section title={t('agent_sec_findings')} tag={(last('findings') as unknown as { findings: Findings }).findings.source === 'llm' ? 'LLM' : t('agent_fallback')}>
          <ul className="text-sm" style={{ margin: '0 0 8px 18px' }}>
            {((last('findings') as unknown as { findings: Findings }).findings.findings ?? []).map((f, i) => <li key={i}>{f}</li>)}
          </ul>
          {(last('findings') as unknown as { findings: Findings }).findings.best_option && (
            <div className="text-xs muted">
              {t('agent_best')}: <code>{(last('findings') as unknown as { findings: Findings }).findings.best_option!.run_id}</code> · {(last('findings') as unknown as { findings: Findings }).findings.best_option!.strategy} · {(last('findings') as unknown as { findings: Findings }).findings.best_option!.why}
            </div>
          )}
        </Section>
      )}

      {/* Replication */}
      {last('replication') && (
        <Section title={t('agent_sec_replication')}
                 tag={(last('replication') as unknown as { replication: Rep | null }).replication ? ((last('replication') as unknown as { replication: Rep }).replication.stable ? t('trust_rep_stable') : t('trust_rep_unstable')) : t('agent_skipped')}
                 tone={(last('replication') as unknown as { replication: Rep | null }).replication?.stable === false ? 'red' : 'green'}>
          <div className="text-xs">{(last('replication') as unknown as { replication: Rep | null }).replication?.verdict ?? t('agent_rep_skipped_why')}</div>
        </Section>
      )}

      {/* Critique */}
      {last('critique') && (
        <Section title={t('agent_sec_critique')}
                 tag={`${(last('critique') as unknown as { critique: Critique }).critique.verdict} · ${Math.round(((last('critique') as unknown as { critique: Critique }).critique.confidence ?? 0) * 100)}%`}
                 tone={verdictTone((last('critique') as unknown as { critique: Critique }).critique.verdict)}>
          {((last('critique') as unknown as { critique: Critique }).critique.issues ?? []).map((it, i) => (
            <div key={i} className="text-xs" style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              <span className={`tag ${it.severity === 'high' ? 'red' : it.severity === 'medium' ? 'amber' : ''}`} style={{ flexShrink: 0 }}>{it.severity}</span>
              <span><b>{it.issue}</b>{it.implication ? ` — ${it.implication}` : ''}</span>
            </div>
          ))}
          {((last('critique') as unknown as { critique: Critique }).critique.what_would_settle_it ?? []).length > 0 && (
            <div className="text-xs muted" style={{ marginTop: 8 }}>
              {t('agent_settle')}: {((last('critique') as unknown as { critique: Critique }).critique.what_would_settle_it ?? []).join('；')}
            </div>
          )}
        </Section>
      )}

      {last('done') && (
        <div className="text-xs muted" style={{ marginTop: 8 }}>
          {t('agent_done_note')} · {String((last('done') as unknown as { conclusion?: string }).conclusion ?? '')}
        </div>
      )}
      {last('error') && <div className="text-xs" style={{ color: 'var(--red)' }}>{String(last('error')!.error)}</div>}
    </div>
  );
}

// ── small helpers ─────────────────────────────────────────────────────────
interface Plan { hypothesis: string; stop_condition?: string; source?: string; experiments: Array<{ label: string; why?: string; config_patch?: Record<string, unknown> }> }
interface Findings { findings: string[]; best_option?: { run_id: string; strategy: string; why: string } | null; source?: string }
interface Critique { verdict: string; confidence?: number; issues?: Array<{ severity: string; issue: string; implication?: string }>; what_would_settle_it?: string[] }
interface Rep { stable: boolean | null; verdict: string }
interface Report { ok: boolean; blocking: Array<{ detail: string }>; warnings: Array<{ detail: string }> }
interface ExperimentEvent { label: string; run_id: string; cached?: boolean; metrics?: { strategies: Record<string, { role: string; approval_rate?: number; bad_rate?: number; raroc?: number }> } }

function verdictTone(v: string) {
  return v === 'supported' ? 'green' : v === 'partially_supported' ? 'amber' : v === 'not_supported' ? 'red' : '';
}

function Section({ title, tag, tone, children }: { title: string; tag?: string; tone?: string; children: React.ReactNode }) {
  return (
    <div className="card mb16">
      <div className="card-hd" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div className="card-title">{title}</div>
        {tag && <span className={`tag ${tone ?? 'blue'}`}>{tag}</span>}
      </div>
      <div className="card-body">{children}</div>
    </div>
  );
}

function PlanView({ plan, t }: { plan: Plan; t: (k: string) => string }) {
  return (
    <>
      <div className="text-sm" style={{ marginBottom: 6 }}><b>{t('agent_hypothesis')}</b>：{plan.hypothesis}</div>
      {plan.stop_condition && <div className="text-xs muted" style={{ marginBottom: 8 }}><b>{t('agent_stop_cond')}</b>：{plan.stop_condition}</div>}
      <table className="data-table">
        <thead><tr><th>{t('agent_run_label')}</th><th>{t('agent_patch')}</th><th>{t('agent_why')}</th></tr></thead>
        <tbody>
          {plan.experiments.map((e, i) => (
            <tr key={i}>
              <td>{e.label}</td>
              <td><code style={{ fontSize: 11 }}>{JSON.stringify(e.config_patch ?? {})}</code></td>
              <td className="text-xs">{e.why ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
