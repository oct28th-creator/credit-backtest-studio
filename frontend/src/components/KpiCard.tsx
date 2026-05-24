import React from 'react';

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

function deltaTone(delta: number, higherIsBetter: boolean): 'up' | 'dn' | 'fl' {
  if (Math.abs(delta) < 0.0001) return 'fl';
  const isGood = higherIsBetter ? delta > 0 : delta < 0;
  return isGood ? 'up' : 'dn';
}

export default function KpiCard({ label, value, unit, delta, higherIsBetter = true, compareRows, highlight }: KpiCardProps) {
  return (
    <div
      className="kpi"
      style={highlight ? { borderColor: 'var(--blue)', borderWidth: 2 } : undefined}
    >
      <div className="kpi-lbl">{label}</div>
      <div className="kpi-row">
        <span className="kpi-val num">
          {value}
          {unit && <span style={{ fontSize: 14, fontWeight: 600, marginLeft: 1 }}>{unit}</span>}
        </span>
        {delta !== undefined && (
          <span className={`kpi-dl ${deltaTone(delta, higherIsBetter)}`}>
            {formatDelta(delta)}
          </span>
        )}
      </div>
      {compareRows && compareRows.length > 0 && (
        <div className="kpi-cmp">
          {compareRows.map(row => `${row.version}: ${row.value}`).join(' · ')}
        </div>
      )}
    </div>
  );
}
