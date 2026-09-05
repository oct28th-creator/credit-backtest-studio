/**
 * The API client falls back to demo fixtures when the backend is unreachable.
 * That fallback is only acceptable if it is impossible to miss, so these tests
 * pin the announcement, not the fallback itself.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { getApiStatus, markDown, markLive, subscribeApiStatus } from '../../src/api/status';

describe('api status', () => {
  beforeEach(() => {
    markLive();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  it('starts live', () => {
    expect(getApiStatus().live).toBe(true);
  });

  it('records which call failed and why', () => {
    markDown('/experiments/run', new Error('HTTP 404'));
    const s = getApiStatus();
    expect(s.live).toBe(false);
    expect(s.lastPath).toBe('/experiments/run');
    expect(s.lastError).toBe('HTTP 404');
  });

  it('notifies subscribers on the way down and back up', () => {
    const seen: boolean[] = [];
    const off = subscribeApiStatus(s => seen.push(s.live));
    markDown('/samples', new Error('Failed to fetch'));
    markLive();
    off();
    expect(seen).toEqual([false, true]);
  });

  it('does not re-notify for the same repeated failure', () => {
    const seen: boolean[] = [];
    markDown('/samples', new Error('Failed to fetch'));
    const off = subscribeApiStatus(s => seen.push(s.live));
    markDown('/samples', new Error('Failed to fetch'));
    off();
    expect(seen).toHaveLength(0);
  });

  it('leaves a console breadcrumb naming the endpoint', () => {
    markDown('/experiments/abc/reslice', new Error('HTTP 500'));
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('/experiments/abc/reslice'),
    );
  });
});
