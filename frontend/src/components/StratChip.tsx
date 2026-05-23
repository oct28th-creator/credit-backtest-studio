import React from 'react';
import { useTranslation } from 'react-i18next';
import type { StrategyRole } from '../types';
import { STRAT_COLORS } from '../data/mockData';

interface StratChipProps {
  id: string;
  role: StrategyRole;
  size?: 'sm' | 'md' | 'lg';
}

function getRoleColor(id: string): string {
  for (const [key, color] of Object.entries(STRAT_COLORS)) {
    if (id === key) return color;
  }
  return '#7a6a55';
}

function getRoleBg(id: string): string {
  const color = getRoleColor(id);
  // lighten for bg
  const map: Record<string, string> = {
    '#7a6a55': '#f0ebe5',
    '#1f5d6d': '#e3f0f3',
    '#bf6b3f': '#faeee6',
    '#6c5aa6': '#ede9f8',
  };
  return map[color] ?? '#f0ebe5';
}

export default function StratChip({ id, role, size = 'md' }: StratChipProps) {
  const { t } = useTranslation();

  const roleLabel = role === 'challenger' ? t('role_challenger')
    : role === 'champion' ? t('role_champion')
    : t('role_beta');

  const color = getRoleColor(id);
  const bg = getRoleBg(id);

  const sizeStyles: Record<string, React.CSSProperties> = {
    sm: { fontSize: 11, padding: '2px 7px', gap: 4 },
    md: { fontSize: 12, padding: '3px 10px', gap: 6 },
    lg: { fontSize: 14, padding: '5px 14px', gap: 8 },
  };

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: 20,
        background: bg,
        color: color,
        fontWeight: 600,
        border: `1.5px solid ${color}22`,
        ...sizeStyles[size],
      }}
    >
      <span
        style={{
          width: size === 'sm' ? 6 : size === 'lg' ? 9 : 7,
          height: size === 'sm' ? 6 : size === 'lg' ? 9 : 7,
          borderRadius: '50%',
          background: color,
          flexShrink: 0,
        }}
      />
      <span style={{ opacity: 0.75 }}>{roleLabel}</span>
      <span style={{ fontFamily: 'monospace' }}>{id}</span>
    </span>
  );
}
