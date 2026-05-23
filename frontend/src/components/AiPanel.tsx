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

  return (
    <div className="ai-panel">
      {/* Header */}
      <div className="ai-panel-header">
        <div className="ai-panel-title">
          <Icon name="sparkles" size={16} style={{ color: 'var(--purple)' }} />
          <span>{layerLabel} · {t('ai_title_prefix')}</span>
          <span className="ai-badge">{t('ai_badge')}</span>
        </div>
        <div className="ai-panel-actions">
          <button className="btn-ghost btn-sm" onClick={onRerun} disabled={state.loading} type="button">
            <Icon name="refresh" size={14} />
            {t('ai_rerun')}
          </button>
          <button className="btn-ghost btn-sm" onClick={onClose} type="button">
            <Icon name="x" size={14} />
            {t('ai_close')}
          </button>
        </div>
      </div>

      {/* Thinking */}
      <Thinking
        text={state.thinking}
        loading={state.loading}
        startTime={state.startTime}
      />

      {/* Analysis */}
      {analysis && (
        <div className="ai-analysis">
          {analysis.findings.length > 0 && (
            <div className="ai-section">
              <div className="ai-section-title ai-findings-title">
                <Icon name="info" size={14} />
                {t('ai_findings')}
              </div>
              <ul className="ai-list">
                {analysis.findings.map((f, i) => (
                  <li key={i} className="ai-finding">{f}</li>
                ))}
              </ul>
            </div>
          )}
          {analysis.warnings.length > 0 && (
            <div className="ai-section">
              <div className="ai-section-title ai-warnings-title">
                <Icon name="warn" size={14} />
                {t('ai_warnings')}
              </div>
              <ul className="ai-list">
                {analysis.warnings.map((w, i) => (
                  <li key={i} className="ai-warning">{w}</li>
                ))}
              </ul>
            </div>
          )}
          {analysis.recommendations.length > 0 && (
            <div className="ai-section">
              <div className="ai-section-title ai-recs-title">
                <Icon name="sparkles" size={14} />
                {t('ai_recommendations')}
              </div>
              <ul className="ai-list">
                {analysis.recommendations.map((r, i) => (
                  <li key={i} className="ai-recommendation">{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Chat */}
      {analysis && (
        <div className="ai-chat">
          <div className="ai-chat-messages">
            {chat.map((msg, i) => (
              <div key={i} className={`ai-chat-msg ai-chat-${msg.role}`}>
                <div className="ai-chat-bubble">{msg.content}</div>
              </div>
            ))}
            {chatLoading && (
              <div className="ai-chat-msg ai-chat-ai">
                <div className="ai-chat-bubble ai-chat-loading">
                  <span className="dots-spinner" />
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
          <div className="ai-chat-input-row">
            <input
              className="ai-chat-input"
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
              placeholder={t('ai_chat_placeholder')}
              disabled={chatLoading}
            />
            <button
              className="btn-primary btn-sm ai-chat-send"
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
