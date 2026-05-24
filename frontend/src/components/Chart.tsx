import React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  ArcElement,
} from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';
import { Line, Bar } from 'react-chartjs-2';
import { STRAT_COLORS } from '../data/mockData';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, Title, Tooltip, Legend, Filler, ArcElement,
  annotationPlugin
);

const FONT = "'Inter', 'system-ui', sans-serif";
const TICK_COLOR = '#9d9189';
const GRID_COLOR = '#ede8e4';

function baseLineOptions(title?: string) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { font: { family: FONT, size: 11 }, color: TICK_COLOR, boxWidth: 12 } },
      title: title ? { display: true, text: title, font: { family: FONT, size: 12 }, color: '#3d3530' } : { display: false },
    },
    scales: {
      x: { ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
      y: { ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
    },
  };
}

// ── ROC Curve ──────────────────────────────────────────────────────────────────
interface RocChartProps {
  roc: Record<string, Array<{ fpr: number; tpr: number }>>;
  aucs: Record<string, number>;
  title?: string;
}

export function RocChart({ roc, aucs, title }: RocChartProps) {
  const datasets = Object.entries(roc).map(([version, pts]) => {
    const color = STRAT_COLORS[version as keyof typeof STRAT_COLORS] ?? '#888';
    return {
      label: `${version} (AUC=${aucs[version]?.toFixed(2) ?? '?'})`,
      data: pts.map(p => ({ x: p.fpr, y: p.tpr })),
      borderColor: color,
      backgroundColor: color + '20',
      fill: true,
      tension: 0.3,
      pointRadius: 2,
    };
  });

  // Diagonal reference
  datasets.push({
    label: 'Random',
    data: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
    borderColor: '#d4ccc8' as string,
    backgroundColor: 'transparent',
    fill: false,
    tension: 0,
    pointRadius: 0,
  } as unknown as typeof datasets[0]);

  return (
    <div style={{ height: 260 }}>
      <Line
        data={{ datasets }}
        options={{
          ...baseLineOptions(title),
          parsing: false,
          scales: {
            x: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'FPR', font: { family: FONT, size: 11 } }, ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
            y: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'TPR', font: { family: FONT, size: 11 } }, ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
          },
        }}
      />
    </div>
  );
}

// ── Calibration Chart ──────────────────────────────────────────────────────────
interface CalibrationChartProps {
  calibration: Record<string, Array<{ pd_pred: number; actual: number }>>;
  title?: string;
}

export function CalibrationChart({ calibration, title }: CalibrationChartProps) {
  const datasets = Object.entries(calibration).map(([version, pts]) => {
    const color = STRAT_COLORS[version as keyof typeof STRAT_COLORS] ?? '#888';
    return {
      label: version,
      data: pts.map(p => ({ x: p.pd_pred, y: p.actual })),
      borderColor: color,
      backgroundColor: color + '30',
      tension: 0.3,
      pointRadius: 3,
    };
  });
  // Perfect calibration line
  datasets.push({
    label: 'Perfect',
    data: [{ x: 0, y: 0 }, { x: 0.3, y: 0.3 }],
    borderColor: '#d4ccc8' as string,
    backgroundColor: 'transparent',
    tension: 0,
    pointRadius: 0,
    borderDash: [4, 4],
  } as unknown as typeof datasets[0]);

  return (
    <div style={{ height: 220 }}>
      <Line
        data={{ datasets }}
        options={{
          ...baseLineOptions(title),
          parsing: false,
          scales: {
            x: { type: 'linear', title: { display: true, text: 'Predicted PD', font: { family: FONT, size: 11 } }, ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
            y: { type: 'linear', title: { display: true, text: 'Actual Bad Rate', font: { family: FONT, size: 11 } }, ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
          },
        }}
      />
    </div>
  );
}

// ── PSI Bar Chart ──────────────────────────────────────────────────────────────
interface PsiBarChartProps {
  data: Array<{ month: string; psi: number; tone: string }>;
  title?: string;
}

export function PsiBarChart({ data, title }: PsiBarChartProps) {
  const colors = data.map(d => d.tone === 'red' ? '#9b2335' : d.tone === 'amber' ? '#b5771a' : '#2d6a4f');
  return (
    <div style={{ height: 200 }}>
      <Bar
        data={{
          labels: data.map(d => d.month),
          datasets: [{
            label: 'PSI',
            data: data.map(d => d.psi),
            backgroundColor: colors,
            borderRadius: 4,
          }],
        }}
        options={{
          ...baseLineOptions(title),
          plugins: {
            ...(baseLineOptions(title).plugins),
            annotation: {
              annotations: {
                line010: {
                  type: 'line', yMin: 0.10, yMax: 0.10,
                  borderColor: '#b5771a', borderWidth: 1.5, borderDash: [4, 4],
                  label: { content: '0.10', display: true, position: 'start', font: { size: 10 } },
                },
                line025: {
                  type: 'line', yMin: 0.25, yMax: 0.25,
                  borderColor: '#9b2335', borderWidth: 1.5, borderDash: [4, 4],
                  label: { content: '0.25', display: true, position: 'start', font: { size: 10 } },
                },
              },
            },
          },
        }}
      />
    </div>
  );
}

// ── Vintage Line Chart ──────────────────────────────────────────────────────────
interface VintageLineChartProps {
  data: Array<Record<string, number>>;
  versions: string[];
  title?: string;
}

export function VintageLineChart({ data, versions, title }: VintageLineChartProps) {
  const datasets = versions.map(v => {
    const color = STRAT_COLORS[v as keyof typeof STRAT_COLORS] ?? '#888';
    return {
      label: v,
      data: data.map(d => d[v] ?? 0),
      borderColor: color,
      backgroundColor: color + '20',
      tension: 0.3,
      pointRadius: 3,
    };
  });
  return (
    <div style={{ height: 220 }}>
      <Line
        data={{ labels: data.map(d => `MOB${d.mob}`), datasets }}
        options={baseLineOptions(title)}
      />
    </div>
  );
}

// ── FPD Bar Chart ──────────────────────────────────────────────────────────────
interface FpdBarChartProps {
  data: Array<Record<string, number | string>>;
  versions: string[];
  title?: string;
}

export function FpdBarChart({ data, versions, title }: FpdBarChartProps) {
  const datasets = versions.map(v => {
    const color = STRAT_COLORS[v as keyof typeof STRAT_COLORS] ?? '#888';
    return {
      label: v,
      data: data.map(d => d[v] as number),
      backgroundColor: color + 'cc',
      borderRadius: 3,
    };
  });
  return (
    <div style={{ height: 200 }}>
      <Bar
        data={{ labels: data.map(d => d.month as string), datasets }}
        options={{ ...baseLineOptions(title), plugins: { ...baseLineOptions(title).plugins } }}
      />
    </div>
  );
}

// ── RAROC Band Chart ──────────────────────────────────────────────────────────
interface RarocBandChartProps {
  data: Record<string, Array<{ band: string; raroc: number }>>;
  title?: string;
}

export function RarocBandChart({ data, title }: RarocBandChartProps) {
  const versions = Object.keys(data);
  const bands = data[versions[0]]?.map(d => d.band) ?? [];
  const datasets = versions.map(v => {
    const color = STRAT_COLORS[v as keyof typeof STRAT_COLORS] ?? '#888';
    return {
      label: v,
      data: data[v].map(d => d.raroc),
      backgroundColor: color + 'cc',
      borderRadius: 3,
    };
  });
  return (
    <div style={{ height: 220 }}>
      <Bar data={{ labels: bands, datasets }} options={{ ...baseLineOptions(title) }} />
    </div>
  );
}

// ── Frontier Chart ──────────────────────────────────────────────────────────────
interface FrontierChartProps {
  data: Array<Record<string, number>>;
  title?: string;
}

export function FrontierChart({ data, title }: FrontierChartProps) {
  return (
    <div style={{ height: 220 }}>
      <Line
        data={{
          datasets: [{
            label: 'Pareto Frontier',
            data: data.map(d => ({ x: d.approval_rate, y: d.avg_profit })),
            borderColor: '#bf6b3f',
            backgroundColor: '#bf6b3f30',
            fill: false,
            tension: 0.3,
            pointRadius: 5,
            pointBackgroundColor: '#bf6b3f',
          }],
        }}
        options={{
          ...baseLineOptions(title),
          parsing: false,
          scales: {
            x: { type: 'linear', title: { display: true, text: 'Approval Rate', font: { family: FONT, size: 11 } }, ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR, callback: (v) => `${(Number(v) * 100).toFixed(0)}%` }, grid: { color: GRID_COLOR } },
            y: { type: 'linear', title: { display: true, text: 'Avg Profit (¥)', font: { family: FONT, size: 11 } }, ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
          },
        }}
      />
    </div>
  );
}

// ── DI Ratio Chart ──────────────────────────────────────────────────────────────
interface DiRatioChartProps {
  groups: Array<{ label: string; value: number }>;
  title?: string;
}

export function DiRatioChart({ groups, title }: DiRatioChartProps) {
  const colors = groups.map(g => g.value < 0.80 ? '#9b2335cc' : g.value < 0.85 ? '#b5771acc' : '#2d6a4fcc');
  return (
    <div style={{ height: Math.max(180, groups.length * 44) }}>
      <Bar
        data={{
          labels: groups.map(g => g.label),
          datasets: [{
            label: 'DI Ratio',
            data: groups.map(g => g.value),
            backgroundColor: colors,
            borderRadius: 4,
          }],
        }}
        options={{
          ...baseLineOptions(title),
          indexAxis: 'y' as const,
          scales: {
            x: { min: 0, max: 1.1, ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
            y: { ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
          },
          plugins: {
            ...baseLineOptions(title).plugins,
            annotation: {
              annotations: {
                threshold: {
                  type: 'line', xMin: 0.80, xMax: 0.80,
                  borderColor: '#9b2335', borderWidth: 2, borderDash: [5, 5],
                  label: { content: '0.80', display: true, position: 'start', color: '#9b2335', font: { size: 10 } },
                },
              },
            },
          },
        }}
      />
    </div>
  );
}

// ── Roll Rate Chart ──────────────────────────────────────────────────────────────
interface RollRateChartProps {
  data: Record<string, { m0_m1: number; m1_m2: number; m2_m3plus: number }>;
  title?: string;
}

export function RollRateChart({ data, title }: RollRateChartProps) {
  const versions = Object.keys(data);
  const bands = ['M0→M1', 'M1→M2', 'M2→M3+'];
  const datasets = versions.map(v => {
    const color = STRAT_COLORS[v as keyof typeof STRAT_COLORS] ?? '#888';
    return {
      label: v,
      data: [data[v].m0_m1, data[v].m1_m2, data[v].m2_m3plus],
      backgroundColor: color + 'cc',
      borderRadius: 3,
    };
  });
  return (
    <div style={{ height: 200 }}>
      <Bar data={{ labels: bands, datasets }} options={baseLineOptions(title)} />
    </div>
  );
}

// ── CSI Bar Chart ──────────────────────────────────────────────────────────────
interface CsiBarChartProps {
  data: Array<{ feature: string; csi: number }>;
  title?: string;
}

export function CsiBarChart({ data, title }: CsiBarChartProps) {
  const colors = data.map(d => d.csi >= 0.25 ? '#9b2335cc' : d.csi >= 0.10 ? '#b5771acc' : '#2d6a4fcc');
  return (
    <div style={{ height: Math.max(180, data.length * 36) }}>
      <Bar
        data={{
          labels: data.map(d => d.feature),
          datasets: [{ label: 'CSI', data: data.map(d => d.csi), backgroundColor: colors, borderRadius: 3 }],
        }}
        options={{
          ...baseLineOptions(title),
          indexAxis: 'y' as const,
          scales: {
            x: { ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
            y: { ticks: { font: { family: FONT, size: 10 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
          },
          plugins: {
            ...baseLineOptions(title).plugins,
            annotation: {
              annotations: {
                warnLine: {
                  type: 'line', xMin: 0.10, xMax: 0.10,
                  borderColor: '#b5771a', borderWidth: 1.5, borderDash: [4, 4],
                },
                critLine: {
                  type: 'line', xMin: 0.25, xMax: 0.25,
                  borderColor: '#9b2335', borderWidth: 1.5, borderDash: [4, 4],
                },
              },
            },
          },
        }}
      />
    </div>
  );
}

// ── Rejection Reason Chart ──────────────────────────────────────────────────────
interface RejectionChartProps {
  data: Record<string, Array<{ reason: string; pct: number }>>;
  selectedVersion: string;
  title?: string;
}

export function RejectionChart({ data, selectedVersion, title }: RejectionChartProps) {
  const vData = data[selectedVersion] ?? [];
  const color = STRAT_COLORS[selectedVersion as keyof typeof STRAT_COLORS] ?? '#888';
  return (
    <div style={{ height: Math.max(180, vData.length * 40) }}>
      <Bar
        data={{
          labels: vData.map(d => d.reason),
          datasets: [{
            label: selectedVersion,
            data: vData.map(d => d.pct),
            backgroundColor: color + 'cc',
            borderRadius: 3,
          }],
        }}
        options={{
          ...baseLineOptions(title),
          indexAxis: 'y' as const,
          scales: {
            x: { min: 0, max: 1, ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR, callback: (v) => `${(Number(v) * 100).toFixed(0)}%` }, grid: { color: GRID_COLOR } },
            y: { ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
          },
        }}
      />
    </div>
  );
}

// ── SHAP Bar Chart ──────────────────────────────────────────────────────────────
interface ShapChartProps {
  data: Array<{ feature: string; shap: number }>;
  title?: string;
}

export function ShapChart({ data, title }: ShapChartProps) {
  const sorted = [...data].sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap));
  const colors = sorted.map(d => d.shap >= 0 ? '#2d6a4fcc' : '#9b2335cc');
  return (
    <div style={{ height: Math.max(180, sorted.length * 36) }}>
      <Bar
        data={{
          labels: sorted.map(d => d.feature),
          datasets: [{ label: 'SHAP', data: sorted.map(d => d.shap), backgroundColor: colors, borderRadius: 3 }],
        }}
        options={{
          ...baseLineOptions(title),
          indexAxis: 'y' as const,
          scales: {
            x: { ticks: { font: { family: FONT, size: 11 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
            y: { ticks: { font: { family: FONT, size: 10 }, color: TICK_COLOR }, grid: { color: GRID_COLOR } },
          },
        }}
      />
    </div>
  );
}
