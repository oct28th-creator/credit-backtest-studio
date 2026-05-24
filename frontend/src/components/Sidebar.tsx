import React from 'react';
import { useTranslation } from 'react-i18next';
import type { Screen } from '../types';
import Icon from './Icon';

interface SidebarProps {
  screen: Screen;
  onNav: (screen: Screen) => void;
  aiOn: boolean;
  onToggleAi: () => void;
}

const NAV_ITEMS: Array<{ id: Screen; icon: Parameters<typeof Icon>[0]['name']; labelKey: string; badge?: string }> = [
  { id: 'config',  icon: 'play',  labelKey: 'sb_new' },
  { id: 'list',    icon: 'list',  labelKey: 'sb_list', badge: 'AI' },
  { id: 'history', icon: 'chart', labelKey: 'sb_trends' },
];

export default function Sidebar({ screen, onNav, aiOn, onToggleAi }: SidebarProps) {
  const { t } = useTranslation();
  const isActive = (id: Screen) => screen === id || (screen === 'results' && id === 'config');

  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <div className="sb-logo">A</div>
        <div className="sb-wordmark">
          <strong>BackTest Studio</strong>
          <span>BackTest · v2</span>
        </div>
      </div>

      <div className="sb-sec">{t('sb_section')}</div>

      {NAV_ITEMS.map(item => (
        <div
          key={item.id}
          className={`sb-item ${isActive(item.id) ? 'on' : ''}`}
          onClick={() => onNav(item.id)}
        >
          <Icon name={item.icon} size={15} />
          {t(item.labelKey)}
          {item.badge && <span className="sb-badge">{item.badge}</span>}
        </div>
      ))}

      <div className="sb-foot">
        <div className={`sb-ai ${aiOn ? 'on' : ''}`} onClick={onToggleAi}>
          <span className={`ai-dot ${aiOn ? 'on' : 'off'}`} />
          {t('sb_ai_label')} {aiOn ? t('sb_ai_on') : t('sb_ai_off')}
        </div>
      </div>
    </aside>
  );
}
