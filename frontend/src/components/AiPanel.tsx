import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { AIAnalysis, ChatMessage, Language } from '../types';
import type { AIState } from '../hooks/useAI';
import Thinking from './Thinking';
import Icon from './Icon';
import API from '../api/client';

interface AiPanelProps {
  layer: string;
  layerLabel: string;
  runId: string;
  language: Language;
  state: AIState;
  onRerun: () => void;
  onClose: () => void;
}

export default function AiPanel({ layer, layerLabel, runId, language, state, onRerun, onClose }: AiPanelProps) {
  const { t } = useTranslation();
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat]);

  useEffect(() => {
    return () => { if (cleanupRef.current) cleanupRef.current(); };
  }, []);

  function sendMessage() {
    if (!input.trim() || chatLoading) return;
    const userMsg = input.trim();
    setInput('');
    setChat(prev => [...prev, { role: 'user', content: userMsg }]);
    setChatLoading(true);

    let aiContent = '';
    const cleanup = API.streamChat(
      runId,
      userMsg,
      chat.map(m => ({ role: m.role, content: m.content })),
      layer,
      language,
      () => {},
      (chunk) => {
        aiContent += chunk;
        setChat(prev => {
          const next = [...prev];
          if (next.length > 0 && next[next.length - 1].role === 'ai') {
            next[next.length - 1] = { role: 'ai', content: aiContent };
          } else {
            next.push({ role: 'ai', content: aiContent });
          }
          return next;
        });
      },
      () => { setChatLoading(false); cleanupRef.current = null; },
      () => { setChatLoading(false); cleanupRef.current = null; }
    );
    cleanupRef.current = cleanup;
  }

  const { analysis } = state;
  const pill = {
    find: language === 'zh' ? '洞察' : 'Insight',
    warn: language === 'zh' ? '预警' : 'Alert',
    act: language === 'zh' ? '建议' : 'Action',
  };

  return (
    <div className={`ai-panel ai-panel-${layer}`}>
      {/* Header */}
      <div className="ai-panel-hd">
        <div className="ai-panel-title">
          <Icon name="sparkles" size={14} />
          <span>{layerLabel} · {t('ai_title_prefix')}</span>
          <span className="ai-badge">{t('ai_badge')}</span>
        </div>
        <div className="flex gap6 items-c">
          <button className="btn ghost sm" onClick={onRerun} disabled={state.loading} type="button">
            <Icon name="refresh" size={13} />
          </button>
          <button className="btn ghost sm" onClick={onClose} type="button">
            <Icon name="x" size={13} />
          </button>
        </div>
      </div>

      {/* Thinking */}
      {(state.loading || state.thinking) && (
        <div style={{ padding: '12px 14px' }}>
          <Thinking
            text={state.thinking}
            loading={state.loading}
            startTime={state.startTime}
          />
        </div>
      )}

      {/* Analysis */}
      {analysis && (
        <div className="ai-panel-body">
          {analysis.findings.map((f, i) => (
            <div key={`f${i}`} className="ai-row">
              <span className="ai-pill find">{pill.find}</span>
              <span className="ai-text">{f}</span>
            </div>
          ))}
          {analysis.warnings.map((w, i) => (
            <div key={`w${i}`} className="ai-row">
              <span className="ai-pill warn">{pill.warn}</span>
              <span className="ai-text">{w}</span>
            </div>
          ))}
          {analysis.recommendations.map((r, i) => (
            <div key={`r${i}`} className="ai-row">
              <span className="ai-pill act">{pill.act}</span>
              <span className="ai-text">{r}</span>
            </div>
          ))}
        </div>
      )}

      {/* Chat */}
      {analysis && (
        <div className="ai-chat">
          {chat.length > 0 && (
            <div className="ai-msgs">
              {chat.map((msg, i) => (
                <div key={i} className={`ai-msg ${msg.role}`}>{msg.content}</div>
              ))}
              {chatLoading && (
                <div className="ai-msg ai"><span className="dots-spinner" /></div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}
          <div className="ai-input-row">
            <input
              className="ai-input"
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
              placeholder={t('ai_chat_placeholder')}
              disabled={chatLoading}
            />
            <button
              className="ai-send"
              onClick={sendMessage}
              disabled={chatLoading || !input.trim()}
              type="button"
            >
              <Icon name="send" size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
