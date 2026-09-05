/**
 * Backend reachability, made visible.
 *
 * The API client falls back to demo fixtures when a call fails, which keeps
 * the UI usable offline — but silently swapping invented numbers in for real
 * ones is indefensible in a credit tool: every figure on screen would look
 * exactly as authoritative as a measured one. So the fallback now announces
 * itself, and the app shows a banner while it is in effect.
 */
import { useEffect, useState } from 'react';

export interface ApiStatus {
  /** false once any call has fallen back to demo fixtures. */
  live: boolean;
  /** Why the last call failed, e.g. "HTTP 404" or "Failed to fetch". */
  lastError?: string;
  /** Endpoint that failed, for the console breadcrumb. */
  lastPath?: string;
}

let state: ApiStatus = { live: true };
const listeners = new Set<(s: ApiStatus) => void>();

function emit() {
  const snapshot = { ...state };
  listeners.forEach(fn => fn(snapshot));
}

export function getApiStatus(): ApiStatus {
  return { ...state };
}

export function markLive(): void {
  if (state.live) return;
  state = { live: true };
  emit();
}

export function markDown(path: string, err: unknown): void {
  const message = err instanceof Error ? err.message : String(err);
  if (!state.live && state.lastError === message && state.lastPath === path) return;
  state = { live: false, lastError: message, lastPath: path };
  // Leave a breadcrumb: the banner says demo data is showing, the console
  // says which call broke and why.
  console.warn(`[backtest] API 调用失败，已切换为演示数据: ${path} — ${message}`);
  emit();
}

export function subscribeApiStatus(fn: (s: ApiStatus) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useApiStatus(): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>(getApiStatus);
  useEffect(() => subscribeApiStatus(setStatus), []);
  return status;
}
