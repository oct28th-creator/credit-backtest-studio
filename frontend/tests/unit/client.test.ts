/**
 * Tests for the API client: SSE stream parsing (backendStream), the
 * mock-fallback wrapper (streamWithFallback), REST fallbacks, and error
 * extraction. All network access is faked through global fetch.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { API } from '../../src/api/client';
import { MOCK_RUN_RESULT, MOCK_STRATEGIES } from '../../src/data/mockData';

function sseResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  const queue = chunks.map(c => enc.encode(c));
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          queue.length
            ? { done: false, value: queue.shift() }
            : { done: true, value: undefined },
      }),
    },
  } as unknown as Response;
}

interface Collected {
  thinks: string[];
  results: string[];
  done: boolean;
  errs: Error[];
}

function collectStream(
  start: (
    onThink: (c: string) => void,
    onResult: (c: string) => void,
    onDone: () => void,
    onErr: (e: Error) => void,
  ) => () => void,
): Promise<Collected> & { abort: () => void } {
  const out: Collected = { thinks: [], results: [], done: false, errs: [] };
  let abort: () => void = () => {};
  const p = new Promise<Collected>((resolve) => {
    abort = start(
      (c) => out.thinks.push(c),
      (c) => out.results.push(c),
      () => { out.done = true; resolve(out); },
      (e) => { out.errs.push(e); resolve(out); },
    );
  }) as Promise<Collected> & { abort: () => void };
  p.abort = abort;
  return p;
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('backendStream SSE parsing (via streamParseConfig)', () => {
  it('routes thinking and result-config events', async () => {
    fetchMock.mockResolvedValue(sseResponse([
      'data: {"type": "thinking", "content": "parsing"}\n\n',
      'data: {"type": "result", "config": {"challenger": "v2.5-RC"}}\n\n',
      'event: done\ndata: {}\n\n',
    ]));
    const out = await collectStream((t, r, d, e) =>
      API.streamParseConfig('use v2.5', 'en', t, r, d, e));
    expect(out.thinks).toEqual(['parsing']);
    expect(JSON.parse(out.results[0])).toEqual({ challenger: 'v2.5-RC' });
    expect(out.done).toBe(true);
    expect(out.errs).toEqual([]);
  });

  it('reassembles events split across network reads', async () => {
    fetchMock.mockResolvedValue(sseResponse([
      'data: {"type": "thin',
      'king", "content": "ab"}\n',
      '\ndata: {"type": "thinking", "content": "cd"}\n\nevent: done\n\n',
    ]));
    const out = await collectStream((t, r, d, e) =>
      API.streamParseConfig('x', 'en', t, r, d, e));
    expect(out.thinks).toEqual(['ab', 'cd']);
    expect(out.done).toBe(true);
  });

  it('joins consecutive data: lines with newlines per the SSE spec', async () => {
    const payload = '{"type": "thinking",\n "content": "multi"}';
    const wire = payload.split('\n').map(l => `data: ${l}`).join('\n');
    fetchMock.mockResolvedValue(sseResponse([`${wire}\n\nevent: done\n\n`]));
    const out = await collectStream((t, r, d, e) =>
      API.streamParseConfig('x', 'en', t, r, d, e));
    expect(out.thinks).toEqual(['multi']);
  });

  it('skips malformed JSON events without failing the stream', async () => {
    fetchMock.mockResolvedValue(sseResponse([
      'data: this is not json\n\n',
      'data: {"type": "thinking", "content": "ok"}\n\n',
      'event: done\n\n',
    ]));
    const out = await collectStream((t, r, d, e) =>
      API.streamParseConfig('x', 'en', t, r, d, e));
    expect(out.thinks).toEqual(['ok']);
    expect(out.done).toBe(true);
  });

  it('treats [DONE] sentinel as end of stream', async () => {
    fetchMock.mockResolvedValue(sseResponse([
      'data: {"type": "thinking", "content": "a"}\n\n',
      'data: [DONE]\n\n',
      'data: {"type": "thinking", "content": "after-done"}\n\n',
    ]));
    const out = await collectStream((t, r, d, e) =>
      API.streamParseConfig('x', 'en', t, r, d, e));
    expect(out.thinks).toEqual(['a']);
    expect(out.done).toBe(true);
  });

  it('wraps result findings arrays into a JSON payload', async () => {
    fetchMock.mockResolvedValue(sseResponse([
      'data: {"type": "result", "findings": ["f"], "warnings": [], "recommendations": ["r"]}\n\n',
      'event: done\n\n',
    ]));
    const out = await collectStream((t, r, d, e) =>
      API.streamAnalyzeLayer('run1', 'l1', 'en', t, r, d, e));
    expect(JSON.parse(out.results[0])).toEqual(
      { findings: ['f'], warnings: [], recommendations: ['r'] });
  });

  it('streams reply/chunk content through onResult', async () => {
    fetchMock.mockResolvedValue(sseResponse([
      'data: {"type": "chunk", "content": "# Report"}\n\n',
      'data: {"type": "chunk", "content": " body"}\n\n',
      'event: done\n\n',
    ]));
    const out = await collectStream((t, r, d, e) =>
      API.streamReport('run1', 'en', t, r, d, e));
    expect(out.results).toEqual(['# Report', ' body']);
  });

  it('calls onDone when the stream closes without a done event', async () => {
    fetchMock.mockResolvedValue(sseResponse([
      'data: {"type": "thinking", "content": "a"}\n\n',
    ]));
    const out = await collectStream((t, r, d, e) =>
      API.streamParseConfig('x', 'en', t, r, d, e));
    expect(out.done).toBe(true);
  });
});

describe('streamWithFallback', () => {
  it('falls back to the mock stream when the backend fails before any data', async () => {
    vi.useFakeTimers();
    fetchMock.mockRejectedValue(new TypeError('network down'));
    const out: Collected = { thinks: [], results: [], done: false, errs: [] };
    let resolveDone: () => void;
    const doneP = new Promise<void>(r => { resolveDone = r; });
    API.streamParseConfig('hello', 'en',
      c => out.thinks.push(c),
      c => out.results.push(c),
      () => { out.done = true; resolveDone(); },
      e => out.errs.push(e));
    await vi.advanceTimersByTimeAsync(60000);
    await doneP;
    expect(out.errs).toEqual([]);          // error is swallowed by the fallback
    expect(out.thinks.length).toBeGreaterThan(0);
    const config = JSON.parse(out.results.join(''));
    expect(config.challenger).toBe('v2.3'); // mock config payload
    expect(out.done).toBe(true);
  });

  it('ends the stream quietly if the backend fails after producing data', async () => {
    const enc = new TextEncoder();
    let reads = 0;
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () => {
            reads += 1;
            if (reads === 1) {
              return { done: false, value: enc.encode('data: {"type": "thinking", "content": "partial"}\n\n') };
            }
            throw new Error('connection reset');
          },
        }),
      },
    } as unknown as Response);
    const out = await collectStream((t, r, d, e) =>
      API.streamParseConfig('x', 'en', t, r, d, e));
    expect(out.thinks).toEqual(['partial']);
    expect(out.done).toBe(true);   // onErr converted to onDone
    expect(out.errs).toEqual([]);
  });
});

describe('REST fallbacks and error extraction', () => {
  it('listStrategies falls back to mock strategies when the API is down', async () => {
    fetchMock.mockRejectedValue(new TypeError('network down'));
    const res = await API.listStrategies();
    expect(res.strategies).toEqual(MOCK_STRATEGIES);
    expect(res.defaults).toEqual({ challenger: 'v2.3', champion: 'v2.2' });
  });

  it('run falls back to the mock result on HTTP error', async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue({ ok: false, status: 500 } as Response);
    const p = API.run({ challenger: 'v2.3', champion: 'v2.2' } as never);
    await vi.advanceTimersByTimeAsync(3000);
    expect(await p).toEqual(MOCK_RUN_RESULT);
  });

  it('uploadStrategy surfaces the backend detail message', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'syntax error: bad code' }),
    } as unknown as Response);
    await expect(API.uploadStrategy('x', 'def broken(:')).rejects.toThrow(
      'syntax error: bad code');
  });

  it('uploadStrategy falls back to HTTP status when detail is absent', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => { throw new Error('not json'); },
    } as unknown as Response);
    await expect(API.uploadStrategy('x', 'code')).rejects.toThrow('HTTP 502');
  });

  it('getHistory filters the mock fallback by strategy and limit', async () => {
    fetchMock.mockRejectedValue(new TypeError('network down'));
    const items = await API.getHistory({ strategy: 'v2.3', limit: 2 });
    expect(items.length).toBe(2);
    for (const item of items) {
      expect([item.challenger, item.champion]).toContain('v2.3');
    }
  });

  it('getHistory builds the query string for the real endpoint', async () => {
    fetchMock.mockResolvedValue({
      ok: true, status: 200, json: async () => [],
    } as unknown as Response);
    await API.getHistory({ strategy: 'v2.2', sample: 'bf2023', limit: 5 });
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/history?');
    expect(url).toContain('strategy=v2.2');
    expect(url).toContain('sample=bf2023');
    expect(url).toContain('limit=5');
  });
});
