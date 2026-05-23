import React from 'react';
import { STRAT_COLORS } from '../data/mockData';

interface CompareRow {
  version: string;
  value: string | number;
}

interface KpiCardProps {
  label: string;
  value: string | number;
  unit?: string;
  delta?: number;          // positive = numerically higher
  higherIsBetter?: boolean; // true = green when positive delta
  compareRows?: CompareRow[];
  highlight?: boolean;
}

function formatDelta(delta: number): string {
  const sign = delta >= 0 ? '+' : '';
  if (Math.abs(delta) < 0.001) return '±0';
  if (Math.abs(delta) < 1) return sign + (delta * 100).toFixed(1) + 'pp';
  return sign + delta.toFixed(2);
}

function deltaColor(delta: number, higherIsBetter: boolean): string {
  if (Math.abs(delta) < 0.0001) return 'var(--ink-4)';
  const isGood = higherIsBetter ? delta > 0 : delta < 0;
  return isGood ? 'var(--green)' : 'var(--red)';
}

function deltaBg(delta: number, higherIsBetter: boolean): string {
  if (Math.abs(delta) < 0.0001) return 'var(--ink-6)';
  const isGood = higherIsBetter ? delta > 0 : delta < 0;
  return isGood ? 'var(--green-bg)' : 'var(--red-bg)';
}

export default function KpiCard({ label, value, unit, delta, higherIsBetter = true, compareRows, highlight }: KpiCardProps) {
  return (
    <div
      className="kpi-card"
      style={highlight ? { borderColor: 'var(--brand)', borderWidth: 2 } : undefined}
    >
      <div className="kpi-label">{label}</div>
      <div className="kpi-value-row">
        <span className="kpi-value">{value}</span>
        {unit && <span className="kpi-unit">{unit}</span>}
        {delta !== undefined && (
          <span
            className="kpi-delta"
            style={{
              color: deltaColor(delta, higherIsBetter),
              background: deltaBg(delta, higherIsBetter),
            }}
          >
            {formatDelta(delta)}
          </span>
        )}
      </div>
      {compareRows && compareRows.length > 0 && (
        <div className="kpi-compare">
          {compareRows.map(row => {
            const color = STRAT_COLORS[row.version as keyof typeof STRAT_COLORS] ?? 'var(--ink-4)';
            return (
              <div key={row.version} className="kpi-compare-row">
                <span className="kpi-compare-dot" style={{ background: color }} />
                <span className="kpi-compare-version" style={{ color }}>{row.version}</span>
                <span className="kpi-compare-val">{row.value}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
