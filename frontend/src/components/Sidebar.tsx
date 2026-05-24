import React from 'react';
import type { Screen } from '../types';
import Icon from './Icon';

interface SidebarProps {
  screen: Screen;
  onNav: (screen: Screen) => void;
  aiOn: boolean;
  onToggleAi: () => void;
}

const NAV_ITEMS: Array<{ id: Screen; icon: Parameters<typeof Icon>[0]['name']; label: string; badge?: string }> = [
  { id: 'config',  icon: 'play',  label: '新建回测' },
  { id: 'list',    icon: 'list',  label: '实验列表', badge: 'AI' },
  { id: 'history', icon: 'chart', label: '历史趋势' },
];

export default function Sidebar({ screen, onNav, aiOn, onToggleAi }: SidebarProps) {
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

      <div className="sb-sec">回测</div>

      {NAV_ITEMS.map(item => (
        <div
          key={item.id}
          className={`sb-item ${isActive(item.id) ? 'on' : ''}`}
          onClick={() => onNav(item.id)}
        >
          <Icon name={item.icon} size={15} />
          {item.label}
          {item.badge && <span className="sb-badge">{item.badge}</span>}
        </div>
      ))}

      <div className="sb-foot">
        <div className={`sb-ai ${aiOn ? 'on' : ''}`} onClick={onToggleAi}>
          <span className={`ai-dot ${aiOn ? 'on' : 'off'}`} />
          AI 解读 {aiOn ? '已开启' : '已关闭'}
        </div>
      </div>
    </aside>
  );
}
