import React from 'react';
import { useTranslation } from 'react-i18next';
import type { Screen } from '../types';
import Icon from './Icon';

interface SidebarProps {
  screen: Screen;
  onNav: (screen: Screen) => void;
  hasResult: boolean;
}

const NAV_ITEMS: Array<{ id: Screen; icon: Parameters<typeof Icon>[0]['name']; labelKey: string; requiresResult?: boolean }> = [
  { id: 'config', icon: 'gear', labelKey: 'nav_config' },
  { id: 'execution', icon: 'play', labelKey: 'nav_execution' },
  { id: 'results', icon: 'layers', labelKey: 'nav_results', requiresResult: true },
  { id: 'history', icon: 'clock', labelKey: 'nav_history' },
];

export default function Sidebar({ screen, onNav, hasResult }: SidebarProps) {
  const { t } = useTranslation();

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">
          <Icon name="chart" size={20} style={{ color: 'var(--brand)' }} />
        </div>
        <div className="sidebar-logo-text">
          <span className="sidebar-logo-name">{t('app_name')}</span>
          <span className="sidebar-logo-subtitle">{t('subtitle')}</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map(item => {
          const disabled = item.requiresResult && !hasResult;
          const active = screen === item.id;
          return (
            <button
              key={item.id}
              className={`sidebar-item ${active ? 'sidebar-item-active' : ''} ${disabled ? 'sidebar-item-disabled' : ''}`}
              onClick={() => !disabled && onNav(item.id)}
              disabled={disabled}
              type="button"
            >
              <Icon name={item.icon} size={18} />
              <span>{t(item.labelKey)}</span>
              {active && <span className="sidebar-active-indicator" />}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-bottom">
        <div className="sidebar-ai-status">
          <span className="ai-status-dot" />
          <span className="ai-status-label">AI Ready</span>
        </div>
      </div>
    </aside>
  );
}
