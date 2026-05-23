import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from './Icon';

interface ThinkingProps {
  text: string;
  loading: boolean;
  startTime: number | null;
  defaultOpen?: boolean;
}

export default function Thinking({ text, loading, startTime, defaultOpen = false }: ThinkingProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen || loading);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (loading && startTime) {
      timerRef.current = setInterval(() => {
        setElapsed(Date.now() - startTime);
      }, 100);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      if (startTime) setElapsed(Date.now() - startTime);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loading, startTime]);

  // Collapse when done
  useEffect(() => {
    if (!loading && text) {
      setOpen(false);
    }
  }, [loading, text]);

  // Open when loading starts
  useEffect(() => {
    if (loading) setOpen(true);
  }, [loading]);

  const elapsedSec = (elapsed / 1000).toFixed(1);

  if (!text && !loading) return null;

  return (
    <div className="thinking-block">
      <button
        className="thinking-header"
        onClick={() => setOpen(o => !o)}
        type="button"
      >
        <span className="thinking-status">
          {loading ? (
            <span className="thinking-spinner" aria-label="thinking" />
          ) : (
            <span className="thinking-done-dot" />
          )}
          <span className="thinking-label">
            {loading ? t('ai_thinking') : t('ai_thinking_done')}
          </span>
        </span>
        {startTime && (
          <span className="thinking-elapsed">
            {t('ai_elapsed')} {elapsedSec}s
          </span>
        )}
        <span className="thinking-toggle">
          <Icon name={open ? 'chevron_up' : 'chevron_down'} size={14} />
        </span>
      </button>
      {open && text && (
        <div className="thinking-body">
          <pre className="thinking-text">{text}</pre>
        </div>
      )}
    </div>
  );
}
