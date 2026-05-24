import React, { useState, useEffect } from 'react';
import Icon from '../components/Icon';
import API from '../api/client';

interface RunSummary {
  run_id: string;
  challenger: string;
  champion: string;
  beta?: string | null;
  sample_size?: number;
  duration_s?: number;
  timestamp?: string;
  created_at?: string;
}

interface Props {
  onOpen: (runId: string) => void;
  onNewRun: () => void;
}

export default function ExperimentListScreen({ onOpen, onNewRun }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.listRuns().then(setRuns).finally(() => setLoading(false));
  }, []);

  return (
    <div className="page">
      <div className="page-hd">
        <div>
          <div className="page-title">实验列表</div>
          <div className="page-sub">查看和重新加载历史回测结果</div>
        </div>
        <button className="btn primary lg" onClick={onNewRun} type="button">
          <Icon name="plus" size={12} /> 新建回测
        </button>
      </div>

      {loading && (
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <span className="dots"><span className="dot" /><span className="dot" /><span className="dot" /></span>
        </div>
      )}

      {!loading && runs.length === 0 && (
        <div className="card" style={{ padding: 56, textAlign: 'center' }}>
          <div style={{ marginBottom: 12, color: 'var(--ink-3)' }}>
            <Icon name="layers" size={36} />
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-2)', marginBottom: 8 }}>暂无实验记录</div>
          <div className="muted text-sm" style={{ marginBottom: 16 }}>运行第一个回测开始探索</div>
          <button className="btn primary" onClick={onNewRun} type="button">
            <Icon name="play" size={12} /> 开始第一个回测
          </button>
        </div>
      )}

      {!loading && runs.length > 0 && (
        <div className="card">
          <table className="tbl">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Challenger</th>
                <th>Champion</th>
                <th>Beta</th>
                <th className="num">样本量</th>
                <th className="num">耗时</th>
                <th>时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.run_id} style={{ cursor: 'pointer' }} onClick={() => onOpen(r.run_id)}>
                  <td className="num" style={{ fontSize: 11, color: 'var(--blue)' }}>{r.run_id}</td>
                  <td>
                    <span className="strat-chip chal" style={{ padding: '3px 8px', fontSize: 11 }}>
                      <span className="role" style={{ fontSize: 9 }}>Ch</span> {r.challenger}
                    </span>
                  </td>
                  <td>
                    <span className="strat-chip champ" style={{ padding: '3px 8px', fontSize: 11 }}>
                      <span className="role" style={{ fontSize: 9 }}>Cp</span> {r.champion}
                    </span>
                  </td>
                  <td>
                    {r.beta
                      ? <span className="strat-chip beta" style={{ padding: '3px 8px', fontSize: 11 }}><span className="role" style={{ fontSize: 9 }}>β</span> {r.beta}</span>
                      : <span className="muted">—</span>}
                  </td>
                  <td className="num">{(r.sample_size || 0).toLocaleString()}</td>
                  <td className="num text-sm">{r.duration_s ?? '—'}s</td>
                  <td className="text-xs muted">
                    {new Date(r.timestamp ?? r.created_at ?? '').toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </td>
                  <td>
                    <button className="btn ghost sm" type="button" onClick={e => { e.stopPropagation(); onOpen(r.run_id); }}>
                      <Icon name="eye" size={12} />
                    </button>
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
