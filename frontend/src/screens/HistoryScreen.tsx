import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Language, RunHistoryItem, ExperimentTree, ExperimentTreeNode, RunDiff, DiffMetric, RunVerdict } from '../types';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, Title, Tooltip, Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import API from '../api/client';
import Icon from '../components/Icon';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

/**
 * History, three ways.
 *
 * The flat log answers "what have I run". It is the wrong shape for a platform
 * where a single question mints half a dozen runs — the original, three
 * reslices, a repair sweep, a replication. Those belong together, in order,
 * with the verdict on each; that is the tree.
 *
 * And the question a log can never answer — "what actually changed between
 * these two?" — gets its own view, aligned by role and with the config diff
 * printed *above* the metric diff, because a metric delta means nothing until
 * you know which input moved.
 */

interface HistoryScreenProps {
  language?: Language;
  onViewRun?: (runId: string) => void;
}

type Tab = 'list' | 'tree' | 'diff';

const CHART_COLORS = { ks: '#1f5d6d', auc: '#bf6b3f', raroc: '#6c5aa6' };
const FONT = "'Inter', 'system-ui', sans-serif";
const TICK = '#9d9189';
const GRID = '#ede8e4';

const VERDICT_TONE: Record<RunVerdict, string> = {
  clean: 'green', warned: 'amber', blocked: 'red', unknown: 'blue',
};

function trendChart(label: string, data: number[], labels: string[], color: string) {
  return {
    labels,
    datasets: [{
      label, data, borderColor: color, backgroundColor: color + '20',
      fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: color,
    }],
  };
}

const chartOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { ticks: { font: { family: FONT, size: 10 }, color: TICK }, grid: { color: GRID } },
    y: { ticks: { font: { family: FONT, size: 10 }, color: TICK }, grid: { color: GRID } },
  },
};

function fmtValue(v: number | null | undefined, format: DiffMetric['format']): string {
  if (v == null) return '—';
  switch (format) {
    case 'pct': return (v * 100).toFixed(1) + '%';
    case 'pct2': return (v * 100).toFixed(2) + '%';
    case 'num2': return v.toFixed(2);
    case 'num3': return v.toFixed(3);
    case 'num4': return v.toFixed(4);
    case 'money': return Math.round(v).toLocaleString();
    case 'int': return Math.round(v).toLocaleString();
    default: return String(v);
  }
}

function fmtDelta(v: number | null | undefined, format: DiffMetric['format']): string {
  if (v == null) return '—';
  const sign = v > 0 ? '+' : '';
  if (format === 'pct' || format === 'pct2') return `${sign}${(v * 100).toFixed(2)}pp`;
  if (format === 'money' || format === 'int') return sign + Math.round(v).toLocaleString();
  return sign + v.toFixed(format === 'num4' ? 4 : 3);
}

function shortTime(ts?: string): string {
  if (!ts) return '—';
  return ts.slice(0, 16).replace('T', ' ');
}

/** The one badge that decides whether a row is shippable. */
function VerdictTag({ item, t }: { item: RunHistoryItem; t: (k: string) => string }) {
  const v: RunVerdict = item.verdict ?? 'unknown';
  const n = v === 'blocked' ? item.blocking?.length : v === 'warned' ? item.warnings?.length : 0;
  const codes = [...(item.blocking ?? []), ...(item.warnings ?? [])].join(', ');
  return (
    <span className={`tag ${VERDICT_TONE[v]}`} title={codes || undefined}>
      {t(`hist_verdict_${v}`)}{n ? ` · ${n}` : ''}
    </span>
  );
}

function PickButtons({ item, sel, onPick, t }: {
  item: RunHistoryItem;
  sel: { a?: string; b?: string };
  onPick: (slot: 'a' | 'b', runId: string) => void;
  t: (k: string) => string;
}) {
  const isA = sel.a === item.run_id;
  const isB = sel.b === item.run_id;
  return (
    <span style={{ display: 'inline-flex', gap: 4 }}>
      <button className={`btn sm ${isA ? '' : 'ghost'}`} type="button"
              title={t('hist_pick_a')} onClick={() => onPick('a', item.run_id)}>A</button>
      <button className={`btn sm ${isB ? '' : 'ghost'}`} type="button"
              title={t('hist_pick_b')} onClick={() => onPick('b', item.run_id)}>B</button>
    </span>
  );
}

export default function HistoryScreen({ onViewRun }: HistoryScreenProps) {
  const { t, i18n } = useTranslation();
  const zh = i18n.language === 'zh';
  const [tab, setTab] = useState<Tab>('list');
  const [items, setItems] = useState<RunHistoryItem[]>([]);
  const [trees, setTrees] = useState<ExperimentTree[]>([]);
  const [filterStrategy, setFilterStrategy] = useState('');
  const [filterSample, setFilterSample] = useState('');
  const [sel, setSel] = useState<{ a?: string; b?: string }>({});
  const [diff, setDiff] = useState<RunDiff | null>(null);
  const [diffErr, setDiffErr] = useState<string | null>(null);
  const [diffBusy, setDiffBusy] = useState(false);

  useEffect(() => {
    API.getHistory({ limit: 50 }).then(setItems).catch(() => setItems([]));
    API.getTrees(30).then(r => setTrees(r.trees)).catch(() => setTrees([]));
  }, []);

  const filtered = useMemo(() => items.filter(item => {
    if (filterStrategy && item.challenger !== filterStrategy && item.champion !== filterStrategy) return false;
    if (filterSample && item.sample_id !== filterSample) return false;
    return true;
  }), [items, filterStrategy, filterSample]);

  // Charts read forward in time; the table reads newest-first.
  const chartRows = useMemo(() => [...filtered].reverse(), [filtered]);
  const labels = chartRows.map(i => (i.timestamp || '').slice(5, 10));
  const uniqueStrategies = Array.from(new Set(items.flatMap(i => [i.challenger, i.champion])));
  const uniqueSamples = Array.from(new Set(items.map(i => i.sample_id)));

  function pick(slot: 'a' | 'b', runId: string) {
    setSel(prev => {
      const next = { ...prev, [slot]: prev[slot] === runId ? undefined : runId };
      // Never let one run occupy both slots — a diff against itself is noise.
      const other = slot === 'a' ? 'b' : 'a';
      if (next[other] === runId) next[other] = undefined;
      return next;
    });
  }

  async function runDiff() {
    if (!sel.a || !sel.b) return;
    setDiffBusy(true); setDiffErr(null); setDiff(null);
    try {
      setDiff(await API.getDiff(sel.a, sel.b));
      setTab('diff');
    } catch (e) {
      setDiffErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDiffBusy(false);
    }
  }

  const demo = items.some(i => i.demo);

  return (
    <div className="page">
      <div className="page-hd" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div className="page-title">{t('history_title')}</div>
        <div className="layer-tabs" style={{ marginBottom: 0 }}>
          {(['list', 'tree', 'diff'] as Tab[]).map(k => (
            <button key={k} type="button"
                    className={`layer-tab ${tab === k ? 'layer-tab-active' : ''}`}
                    onClick={() => setTab(k)}>
              {t(`hist_tab_${k}`)}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {(sel.a || sel.b) && (
            <>
              <span className="text-xs muted">
                A <code>{sel.a ?? '—'}</code> · B <code>{sel.b ?? '—'}</code>
              </span>
              <button className="btn ghost sm" type="button"
                      onClick={() => setSel(s => ({ a: s.b, b: s.a }))}>{t('hist_swap_ab')}</button>
              <button className="btn ghost sm" type="button"
                      onClick={() => { setSel({}); setDiff(null); }}>{t('hist_clear_sel')}</button>
            </>
          )}
          <button className="btn sm" type="button" disabled={!sel.a || !sel.b || diffBusy} onClick={runDiff}>
            {t('hist_compare_go')}
          </button>
        </div>
      </div>

      {tab === 'list' && (
        <>
          <div className="chart-grid chart-grid-3">
            <div className="chart-card">
              <div className="chart-title">{t('history_ks_trend')}</div>
              <div style={{ height: 160 }}>
                <Line data={trendChart('KS', chartRows.map(i => i.l1_ks), labels, CHART_COLORS.ks)} options={chartOpts} />
              </div>
            </div>
            <div className="chart-card">
              <div className="chart-title">{t('history_auc_trend')}</div>
              <div style={{ height: 160 }}>
                <Line data={trendChart('AUC', chartRows.map(i => i.l1_auc), labels, CHART_COLORS.auc)} options={chartOpts} />
              </div>
            </div>
            <div className="chart-card">
              <div className="chart-title">{t('history_raroc_trend')}</div>
              <div style={{ height: 160 }}>
                <Line data={trendChart('RAROC', chartRows.map(i => i.l2_raroc), labels, CHART_COLORS.raroc)} options={chartOpts} />
              </div>
            </div>
          </div>

          <div className="history-filters">
            <div className="filter-group">
              <label className="filter-label">{t('history_filter_strategy')}</label>
              <select className="sel filter-select" value={filterStrategy}
                      onChange={e => setFilterStrategy(e.target.value)}>
                <option value="">{t('all')}</option>
                {uniqueStrategies.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="filter-group">
              <label className="filter-label">{t('history_filter_sample')}</label>
              <select className="sel filter-select" value={filterSample}
                      onChange={e => setFilterSample(e.target.value)}>
                <option value="">{t('all')}</option>
                {uniqueSamples.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>

          <div className="chart-card">
            <div className="chart-title">{t('history_experiment_log')}</div>
            {!filtered.length && <div className="text-xs muted" style={{ padding: 12 }}>{t('hist_empty')}</div>}
            {!!filtered.length && (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table history-table">
                  <thead>
                    <tr>
                      <th>{t('history_run_id')}</th>
                      <th>{t('history_timestamp')}</th>
                      <th>{t('history_challenger')}</th>
                      <th>{t('history_champion')}</th>
                      <th>{t('history_sample')}</th>
                      <th>KS</th><th>AUC</th><th>RAROC</th>
                      <th>{t('hist_verdict_blocked')}</th>
                      <th>A/B</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(item => (
                      <tr key={item.run_id} className="history-row">
                        <td>
                          <code style={{ fontSize: 11 }}>{item.run_id}</code>
                          {item.slice?.value && (
                            <div className="text-xs muted">{t('hist_slice')}: {item.slice.dim}={item.slice.value}</div>
                          )}
                        </td>
                        <td style={{ fontSize: 12 }}>{shortTime(item.timestamp)}</td>
                        <td><span style={{ color: 'var(--chal)', fontWeight: 600 }}>{item.challenger}</span></td>
                        <td><span style={{ color: 'var(--champ)', fontWeight: 600 }}>{item.champion}</span></td>
                        <td style={{ fontSize: 12 }}>{item.sample_id}</td>
                        <td className="num">{item.l1_ks.toFixed(3)}</td>
                        <td className="num">{item.l1_auc.toFixed(3)}</td>
                        <td className="num">{(item.l2_raroc * 100).toFixed(1)}%</td>
                        <td><VerdictTag item={item} t={t} /></td>
                        <td><PickButtons item={item} sel={sel} onPick={pick} t={t} /></td>
                        <td>
                          {onViewRun && !item.demo && (
                            <button className="btn ghost sm" onClick={() => onViewRun(item.run_id)} type="button">
                              <Icon name="eye" size={13} />
                              {t('history_view')}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {demo && <div className="text-xs muted" style={{ marginTop: 8 }}>demo</div>}
          </div>
        </>
      )}

      {tab === 'tree' && (
        <div className="chart-card">
          <div className="chart-title">{t('hist_tab_tree')}</div>
          {!trees.length && <div className="text-xs muted" style={{ padding: 12 }}>{t('hist_empty_tree')}</div>}
          {trees.map(tree => (
            <div key={tree.root_run_id} style={{ marginBottom: 18, paddingBottom: 14, borderBottom: '1px solid var(--bd, #ede8e4)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                <span className="tag blue">{t('hist_thread')}</span>
                <code style={{ fontSize: 11 }}>{tree.root_run_id}</code>
                <span className="text-xs muted">
                  {tree.challenger} vs {tree.champion} · {tree.sample_id} · {tree.n_runs} {t('hist_thread_runs')}
                </span>
                {tree.n_blocked > 0 && <span className="tag red">{tree.n_blocked} {t('hist_verdict_blocked')}</span>}
                {tree.n_clean > 0 && <span className="tag green">{tree.n_clean} {t('hist_verdict_clean')}</span>}
                <span className="text-xs muted" style={{ marginLeft: 'auto' }}>{shortTime(tree.last_at)}</span>
              </div>
              {tree.question && (
                <div className="text-xs" style={{ marginBottom: 4 }}>
                  <b>{t('hist_thread_question')}:</b> {tree.question}
                </div>
              )}
              {tree.finding && (
                <div className="text-xs" style={{ marginBottom: 8 }}>
                  <b>{t('hist_thread_finding')}:</b> {tree.finding}
                </div>
              )}
              {tree.nodes.map(node => (
                <TreeRow key={node.run_id} node={node} sel={sel} onPick={pick}
                         onViewRun={onViewRun} t={t} />
              ))}
            </div>
          ))}
        </div>
      )}

      {tab === 'diff' && (
        <div className="chart-card">
          <div className="chart-title">{t('hist_tab_diff')}</div>
          {diffErr && <div className="text-xs" style={{ color: 'var(--red)' }}>{diffErr}</div>}
          {!diff && !diffErr && <div className="text-xs muted" style={{ padding: 12 }}>{t('hist_compare_hint')}</div>}
          {diff && <DiffView diff={diff} t={t} zh={zh} />}
        </div>
      )}
    </div>
  );
}

function TreeRow({ node, sel, onPick, onViewRun, t }: {
  node: ExperimentTreeNode;
  sel: { a?: string; b?: string };
  onPick: (slot: 'a' | 'b', runId: string) => void;
  onViewRun?: (runId: string) => void;
  t: (k: string) => string;
}) {
  const overrides = Object.entries(node.overrides ?? {})
    .flatMap(([sid, kv]) => Object.entries(kv).map(([k, v]) => `${sid}.${k}=${v}`));
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
      padding: '5px 0 5px ' + (node.depth * 22 + 4) + 'px',
      borderLeft: node.depth ? '2px solid var(--bd, #ede8e4)' : undefined,
      marginLeft: node.depth ? 8 : 0,
    }}>
      <span className="text-xs muted" style={{ width: 14 }}>{node.depth ? '└' : '●'}</span>
      <code style={{ fontSize: 11 }}>{node.run_id}</code>
      <VerdictTag item={node} t={t} />
      {node.slice?.value && (
        <span className="tag blue">{t('hist_slice')} {node.slice.dim}={node.slice.value}</span>
      )}
      {!!overrides.length && <span className="tag amber">{t('hist_override')} {overrides.join(' ')}</span>}
      <span className="text-xs muted">
        {t('hist_apr')} {node.l2_approval_rate != null ? (node.l2_approval_rate * 100).toFixed(1) + '%' : '—'}
        {' · '}{t('hist_bad')} {node.l2_bad_rate != null ? (node.l2_bad_rate * 100).toFixed(2) + '%' : '—'}
        {' · RAROC '}{(node.l2_raroc * 100).toFixed(1)}%
      </span>
      <span className="text-xs muted">{t('hist_by')} {node.created_by}</span>
      <span className="text-xs muted" style={{ marginLeft: 'auto' }}>{shortTime(node.timestamp)}</span>
      <PickButtons item={node} sel={sel} onPick={onPick} t={t} />
      {onViewRun && (
        <button className="btn ghost sm" type="button" onClick={() => onViewRun(node.run_id)}>
          <Icon name="eye" size={13} />
        </button>
      )}
    </div>
  );
}

function DiffView({ diff, t, zh }: { diff: RunDiff; t: (k: string) => string; zh: boolean }) {
  const byLayer = useMemo(() => {
    const groups: Record<string, DiffMetric[]> = {};
    diff.metrics.forEach(m => { (groups[m.layer] ??= []).push(m); });
    return groups;
  }, [diff]);
  const roles = Array.from(new Set(diff.metrics.map(m => m.role)));
  const [role, setRole] = useState(roles.includes('challenger') ? 'challenger' : roles[0]);

  return (
    <div>
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 10 }}>
        {(['a', 'b'] as const).map(slot => {
          const r = diff[slot];
          return (
            <div key={slot} style={{ flex: 1, minWidth: 220 }}>
              <div className="text-xs bold" style={{ marginBottom: 2 }}>
                {slot.toUpperCase()} · <code>{r.run_id}</code>
              </div>
              <div className="text-xs muted">
                {shortTime(r.timestamp)} · {r.challenger} vs {r.champion} · n={r.sample_size?.toLocaleString()}
              </div>
              <div style={{ marginTop: 4 }}><VerdictTag item={r} t={t} /></div>
            </div>
          );
        })}
      </div>

      <div className="text-xs" style={{ marginBottom: 12, lineHeight: 1.7 }}>
        {zh ? diff.note_zh : diff.note_en}
      </div>

      <div className="text-xs bold" style={{ marginBottom: 6 }}>{t('hist_diff_config')}</div>
      {!diff.config_diff.length && <div className="text-xs muted" style={{ marginBottom: 12 }}>{t('hist_diff_none')}</div>}
      {!!diff.config_diff.length && (
        <table className="data-table" style={{ marginBottom: 16 }}>
          <thead>
            <tr><th>{t('hist_diff_field')}</th><th>A</th><th>B</th></tr>
          </thead>
          <tbody>
            {diff.config_diff.map(c => (
              <tr key={c.field}>
                <td>{zh ? c.label_zh : c.label_en}</td>
                <td className="text-xs">{c.a == null ? '—' : typeof c.a === 'object' ? JSON.stringify(c.a) : String(c.a)}</td>
                <td className="text-xs">{c.b == null ? '—' : typeof c.b === 'object' ? JSON.stringify(c.b) : String(c.b)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <div className="text-xs bold">{t('hist_diff_metrics')}</div>
        <div className="layer-tabs" style={{ marginBottom: 0 }}>
          {roles.map(r => (
            <button key={r} type="button" className={`layer-tab ${role === r ? 'layer-tab-active' : ''}`}
                    onClick={() => setRole(r)}>{t(`hist_role_${r}`)}</button>
          ))}
        </div>
      </div>

      {(['l1', 'l2', 'l3', 'l5'] as const).map(layer => {
        const rows = (byLayer[layer] ?? []).filter(m => m.role === role);
        if (!rows.length) return null;
        return (
          <div key={layer} style={{ marginBottom: 12 }}>
            <div className="text-xs muted" style={{ marginBottom: 4 }}>{layer.toUpperCase()}</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th />
                  <th>A · {rows[0].strategy_a}</th>
                  <th>B · {rows[0].strategy_b}</th>
                  <th>{t('hist_diff_delta')}</th>
                  <th>{t('hist_diff_better')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(m => (
                  <tr key={m.key}>
                    <td>{zh ? m.label_zh : m.label_en}</td>
                    <td className="num">{fmtValue(m.a, m.format)}</td>
                    <td className="num">{fmtValue(m.b, m.format)}</td>
                    <td className="num" style={{ color: m.better ? undefined : 'var(--ink-3)' }}>
                      {fmtDelta(m.delta, m.format)}
                    </td>
                    <td>
                      {m.better
                        ? <span className={`tag ${m.better === 'b' ? 'green' : 'blue'}`}>{m.better.toUpperCase()}</span>
                        : <span className="text-xs muted">{t('hist_diff_neutral')}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}
