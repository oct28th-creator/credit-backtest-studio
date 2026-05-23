import { useState, useCallback, useRef } from 'react';
import type { AIAnalysis } from '../types';

export interface AIState {
  thinking: string;
  analysis: AIAnalysis | null;
  loading: boolean;
  open: boolean;
  startTime: number | null;
}

const initialState: AIState = {
  thinking: '',
  analysis: null,
  loading: false,
  open: false,
  startTime: null,
};

export function useAI() {
  const [state, setState] = useState<AIState>(initialState);
  const cleanupRef = useRef<(() => void) | null>(null);

  const trigger = useCallback((streamFn: (
    onThink: (c: string) => void,
    onResult: (c: string) => void,
    onDone: () => void,
    onErr: (e: Error) => void
  ) => (() => void)) => {
    // Cancel any in-flight stream
    if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null; }

    setState({ thinking: '', analysis: null, loading: true, open: true, startTime: Date.now() });

    let thinkBuf = '';
    let resultBuf = '';

    const cleanup = streamFn(
      (chunk) => {
        thinkBuf += chunk;
        setState(s => ({ ...s, thinking: thinkBuf }));
      },
      (chunk) => {
        resultBuf += chunk;
        // Try to parse partial JSON
        try {
          const parsed = JSON.parse(resultBuf) as AIAnalysis;
          setState(s => ({ ...s, analysis: parsed }));
        } catch { /* accumulating */ }
      },
      () => {
        // Done — final parse
        try {
          const parsed = JSON.parse(resultBuf) as AIAnalysis;
          setState(s => ({ ...s, analysis: parsed, loading: false }));
        } catch {
          setState(s => ({ ...s, loading: false }));
        }
        cleanupRef.current = null;
      },
      (_err) => {
        setState(s => ({ ...s, loading: false }));
        cleanupRef.current = null;
      }
    );

    cleanupRef.current = cleanup;
    return cleanup;
  }, []);

  const rerun = useCallback((streamFn: Parameters<typeof trigger>[0]) => {
    setState(s => ({ ...s, thinking: '', analysis: null, loading: true, startTime: Date.now() }));
    return trigger(streamFn);
  }, [trigger]);

  const close = useCallback(() => {
    if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null; }
    setState(initialState);
  }, []);

  return { state, trigger, rerun, close };
}
