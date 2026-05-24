import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Language } from '../types';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, Title, Tooltip, Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import API from '../api/client';
import Icon from '../components/Icon';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

interface HistoryItem {
  run_id: string; timestamp: string; champion: string; challenger: string;
  beta: string | null; sample_id: string; duration_s: number;
  l1_ks: number; l1_auc: number; l2_raroc: number;
}

interface HistoryScreenProps {
  language?: Language;
  onViewRun?: (runId: string) => void;
}

const CHART_COLORS = {
  ks: '#1f5d6d',
  auc: '#bf6b3f',
  raroc: '#6c5aa6',
};

const FONT = "'Inter', 'system-ui', sans-serif";
const TICK = '#9d9189';
const GRID = '#ede8e4';

function trendChart(label: string, data: number[], labels: string[], color: string) {
  return {
    labels,
    datasets: [{
      label,
      data,
      borderColor: color,
      backgroundColor: color + '20',
      fill: true,
      tension: 0.3,
      pointRadius: 4,
      pointBackgroundColor: color,
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

export default function HistoryScreen({ language, onViewRun }: HistoryScreenProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [filterStrategy, setFilterStrategy] = useState('');
  const [filterSample, setFilterSample] = useState('');

  useEffect(() => {
    API.getHistory({ limit: 20 }).then(setItems).catch(() => {});
  }, []);

  const filtered = items.filter(item => {
    if (filterStrategy && item.challenger !== filterStrategy && item.champion !== filterStrategy) return false;
    if (filterSample && item.sample_id !== filterSample) return false;
    return true;
  });

  const labels = filtered.map(i => i.timestamp.slice(0, 10));
  const uniqueStrategies = Array.from(new Set(items.flatMap(i => [i.challenger, i.champion])));
  const uniqueSamples = Array.from(new Set(items.map(i => i.sample_id)));

  return (
    <div className="page">
      <div className="page-hd">
        <div className="page-title">{t('history_title')}</div>
      </div>

      {/* KPI Trend Charts */}
      <div className="chart-grid chart-grid-3">
        <div className="chart-card">
          <div className="chart-title">{t('history_ks_trend')}</div>
          <div style={{ height: 160 }}>
            <Line data={trendChart('KS', filtered.map(i => i.l1_ks), labels, CHART_COLORS.ks)} options={chartOpts} />
          </div>
        </div>
        <div className="chart-card">
          <div className="chart-title">{t('history_auc_trend')}</div>
          <div style={{ height: 160 }}>
            <Line data={trendChart('AUC', filtered.map(i => i.l1_auc), labels, CHART_COLORS.auc)} options={chartOpts} />
          </div>
        </div>
        <div className="chart-card">
          <div className="chart-title">{t('history_raroc_trend')}</div>
          <div style={{ height: 160 }}>
            <Line data={trendChart('RAROC', filtered.map(i => i.l2_raroc), labels, CHART_COLORS.raroc)} options={chartOpts} />
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="history-filters">
        <div className="filter-group">
          <label className="filter-label">{t('history_filter_strategy')}</label>
          <select
            className="sel filter-select"
            value={filterStrategy}
            onChange={e => setFilterStrategy(e.target.value)}
          >
            <option value="">{t('all')}</option>
            {uniqueStrategies.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">{t('history_filter_sample')}</label>
          <select
            className="sel filter-select"
            value={filterSample}
            onChange={e => setFilterSample(e.target.value)}
          >
            <option value="">{t('all')}</option>
            {uniqueSamples.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {/* Experiment Log Table */}
      <div className="chart-card">
        <div className="chart-title">{t('history_experiment_log')}</div>
        <table className="data-table history-table">
          <thead>
            <tr>
              <th>{t('history_run_id')}</th>
              <th>{t('history_timestamp')}</th>
              <th>{t('history_challenger')}</th>
              <th>{t('history_champion')}</th>
              <th>{t('history_sample')}</th>
              <th>KS</th>
              <th>AUC</th>
              <th>RAROC</th>
              <th>{t('history_duration')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map(item => (
              <tr key={item.run_id} className="history-row">
                <td><code style={{ fontSize: 11 }}>{item.run_id}</code></td>
                <td style={{ fontSize: 12 }}>{item.timestamp.slice(0, 16).replace('T', ' ')}</td>
                <td><span style={{ color: 'var(--chal)', fontWeight: 600 }}>{item.challenger}</span></td>
                <td><span style={{ color: 'var(--champ)', fontWeight: 600 }}>{item.champion}</span></td>
                <td style={{ fontSize: 12 }}>{item.sample_id}</td>
                <td>{item.l1_ks.toFixed(2)}</td>
                <td>{item.l1_auc.toFixed(2)}</td>
                <td>{(item.l2_raroc * 100).toFixed(0)}%</td>
                <td style={{ fontSize: 12 }}>{item.duration_s.toFixed(1)}s</td>
                <td>
                  {onViewRun && (
                    <button
                      className="btn ghost sm"
                      onClick={() => onViewRun(item.run_id)}
                      type="button"
                    >
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
    </div>
  );
}
