import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Language } from '../types';
import API from '../api/client';
import Thinking from './Thinking';
import Icon from './Icon';

interface ReportModalProps {
  runId: string;
  language: Language;
  onClose: () => void;
}

export default function ReportModal({ runId, language, onClose }: ReportModalProps) {
  const { t } = useTranslation();
  const [thinking, setThinking] = useState('');
  const [content, setContent] = useState('');
  const [done, setDone] = useState(false);
  const [startTime] = useState(Date.now());
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let thinkBuf = '';
    let contentBuf = '';
    const cleanup = API.streamReport(
      runId,
      language,
      (chunk) => { thinkBuf += chunk; setThinking(thinkBuf); },
      (chunk) => { contentBuf += chunk; setContent(contentBuf); },
      () => { setDone(true); cleanupRef.current = null; },
      () => { setDone(true); cleanupRef.current = null; }
    );
    cleanupRef.current = cleanup;
    return () => { if (cleanupRef.current) cleanupRef.current(); };
  }, [runId, language]);

  function handleDownload() {
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `backtest-report-${runId}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // Simple markdown renderer
  function renderMd(md: string): string {
    return md
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/^/g, '<p>')
      .replace(/$/g, '</p>');
  }

  return (
    <div className="overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal">
        <div className="modal-hd">
          <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, fontSize: 15 }}>
            <Icon name="download" size={16} style={{ color: 'var(--blue)' }} />
            {t('report_title')}
          </span>
          <div className="flex gap8 items-c">
            {done && (
              <button className="btn ghost sm" onClick={handleDownload} type="button">
                <Icon name="download" size={14} />
                {t('report_download')}
              </button>
            )}
            <button className="btn ghost sm" onClick={onClose} type="button">
              <Icon name="x" size={14} />
              {t('report_close')}
            </button>
          </div>
        </div>

        <div className="modal-body">
          <Thinking
            text={thinking}
            loading={!done}
            startTime={startTime}
          />
          {content && (
            <div
              className="report-content"
              dangerouslySetInnerHTML={{ __html: renderMd(content) }}
            />
          )}
          {!content && !done && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 40, color: 'var(--ink-3)' }}>
              <span className="dots-spinner" />
              <span>{t('report_generating')}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
