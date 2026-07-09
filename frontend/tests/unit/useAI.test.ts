/**
 * Tests for the useAI hook: stream lifecycle (trigger/rerun/close/seed),
 * incremental thinking accumulation, JSON result assembly from chunks, and
 * cancellation of in-flight streams.
 */
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAI } from '../../src/hooks/useAI';

type Handlers = {
  onThink: (c: string) => void;
  onResult: (c: string) => void;
  onDone: () => void;
  onErr: (e: Error) => void;
};

/** A manually driven stream: capture the handlers, return a spy cleanup. */
function manualStream() {
  const h = {} as Handlers;
  const cleanup = vi.fn();
  const streamFn = (
    onThink: Handlers['onThink'],
    onResult: Handlers['onResult'],
    onDone: Handlers['onDone'],
    onErr: Handlers['onErr'],
  ) => {
    h.onThink = onThink;
    h.onResult = onResult;
    h.onDone = onDone;
    h.onErr = onErr;
    return cleanup;
  };
  return { h, cleanup, streamFn };
}

describe('useAI', () => {
  it('starts loading and open on trigger', () => {
    const { result } = renderHook(() => useAI());
    const { streamFn } = manualStream();
    act(() => { result.current.trigger(streamFn); });
    expect(result.current.state.loading).toBe(true);
    expect(result.current.state.open).toBe(true);
    expect(result.current.state.thinking).toBe('');
    expect(result.current.state.analysis).toBeNull();
    expect(result.current.state.startTime).not.toBeNull();
  });

  it('accumulates thinking chunks', () => {
    const { result } = renderHook(() => useAI());
    const { h, streamFn } = manualStream();
    act(() => { result.current.trigger(streamFn); });
    act(() => { h.onThink('analysing '); h.onThink('the data'); });
    expect(result.current.state.thinking).toBe('analysing the data');
  });

  it('parses the analysis once the accumulated JSON becomes valid', () => {
    const { result } = renderHook(() => useAI());
    const { h, streamFn } = manualStream();
    act(() => { result.current.trigger(streamFn); });
    act(() => { h.onResult('{"findings": ["f1"], '); });
    expect(result.current.state.analysis).toBeNull(); // still incomplete
    act(() => { h.onResult('"warnings": [], "recommendations": []}'); });
    expect(result.current.state.analysis).toEqual(
      { findings: ['f1'], warnings: [], recommendations: [] });
  });

  it('finishes loading on done and keeps the parsed analysis', () => {
    const { result } = renderHook(() => useAI());
    const { h, streamFn } = manualStream();
    act(() => { result.current.trigger(streamFn); });
    act(() => {
      h.onResult('{"findings": [], "warnings": ["w"], "recommendations": []}');
      h.onDone();
    });
    expect(result.current.state.loading).toBe(false);
    expect(result.current.state.analysis?.warnings).toEqual(['w']);
  });

  it('stops loading without analysis when the result never parses', () => {
    const { result } = renderHook(() => useAI());
    const { h, streamFn } = manualStream();
    act(() => { result.current.trigger(streamFn); });
    act(() => { h.onResult('not json at all'); h.onDone(); });
    expect(result.current.state.loading).toBe(false);
    expect(result.current.state.analysis).toBeNull();
  });

  it('stops loading on stream error', () => {
    const { result } = renderHook(() => useAI());
    const { h, streamFn } = manualStream();
    act(() => { result.current.trigger(streamFn); });
    act(() => { h.onErr(new Error('boom')); });
    expect(result.current.state.loading).toBe(false);
  });

  it('cancels the in-flight stream when triggered again', () => {
    const { result } = renderHook(() => useAI());
    const first = manualStream();
    const second = manualStream();
    act(() => { result.current.trigger(first.streamFn); });
    act(() => { result.current.trigger(second.streamFn); });
    expect(first.cleanup).toHaveBeenCalledTimes(1);
    expect(second.cleanup).not.toHaveBeenCalled();
  });

  it('close aborts the stream and resets state', () => {
    const { result } = renderHook(() => useAI());
    const { h, cleanup, streamFn } = manualStream();
    act(() => { result.current.trigger(streamFn); });
    act(() => { h.onThink('partial'); });
    act(() => { result.current.close(); });
    expect(cleanup).toHaveBeenCalledTimes(1);
    expect(result.current.state).toEqual(
      { thinking: '', analysis: null, loading: false, open: false, startTime: null });
  });

  it('seed opens the panel with a pre-built analysis and no loading', () => {
    const { result } = renderHook(() => useAI());
    const analysis = { findings: ['cached'], warnings: [], recommendations: [] };
    act(() => { result.current.seed(analysis, 'cached thinking'); });
    expect(result.current.state.open).toBe(true);
    expect(result.current.state.loading).toBe(false);
    expect(result.current.state.analysis).toEqual(analysis);
    expect(result.current.state.thinking).toBe('cached thinking');
  });

  it('rerun restarts with cleared thinking and analysis', () => {
    const { result } = renderHook(() => useAI());
    const first = manualStream();
    act(() => { result.current.trigger(first.streamFn); });
    act(() => {
      first.h.onThink('old');
      first.h.onResult('{"findings": [], "warnings": [], "recommendations": []}');
      first.h.onDone();
    });
    const second = manualStream();
    act(() => { result.current.rerun(second.streamFn); });
    expect(result.current.state.thinking).toBe('');
    expect(result.current.state.analysis).toBeNull();
    expect(result.current.state.loading).toBe(true);
  });
});
