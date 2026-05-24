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
    <div className="thinking">
      <div
        className="think-hd"
        onClick={() => setOpen(o => !o)}
        role="button"
      >
        {loading ? (
          <span className="think-spin" aria-label="thinking" />
        ) : (
          <span className="think-dot" style={{ background: text ? 'var(--green)' : 'var(--ink-4)' }} />
        )}
        <span style={{ flex: 1 }}>
          {loading ? t('ai_thinking') : t('ai_thinking_done')}
        </span>
        {startTime && (
          <span className="text-xs muted">{elapsedSec}s</span>
        )}
        <span className="think-arrow" style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}>
          <Icon name="chev_right" size={12} />
        </span>
      </div>
      {open && text && (
        <div className="think-body">
          <pre className="think-text" style={{ margin: 0, fontFamily: 'inherit', whiteSpace: 'pre-wrap' }}>{text}</pre>
        </div>
      )}
    </div>
  );
}
