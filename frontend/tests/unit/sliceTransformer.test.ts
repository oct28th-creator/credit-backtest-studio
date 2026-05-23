import { describe, it, expect } from 'vitest';
import { applyMockSlice, MOCK_RUN_RESULT } from '../../src/data/mockData';

describe('applyMockSlice', () => {
  it('returns original result when no slice is applied', () => {
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: null, slice_value: null });
    expect(result).toStrictEqual(MOCK_RUN_RESULT);
  });

  it('returns a different result when slice is applied', () => {
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'online' });
    expect(result).not.toStrictEqual(MOCK_RUN_RESULT);
  });

  it('preserves run_id from original', () => {
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'online' });
    expect(result.run_id).toBe(MOCK_RUN_RESULT.run_id);
  });

  it('updates config with slice info', () => {
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'online' });
    expect(result.config.slice_dim).toBe('channel');
    expect(result.config.slice_value).toBe('online');
  });

  it('online channel factor > 1 improves KS for challenger', () => {
    const original = MOCK_RUN_RESULT.layers.l1.kpis.find(k => k.version === 'v2.3')!.ks;
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'online' });
    const sliced = result.layers.l1.kpis.find(k => k.version === 'v2.3')!.ks;
    // factor = 1.05 so KS should be higher
    expect(sliced).toBeGreaterThan(original);
  });

  it('offline channel factor < 1 reduces KS for challenger', () => {
    const original = MOCK_RUN_RESULT.layers.l1.kpis.find(k => k.version === 'v2.3')!.ks;
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'offline' });
    const sliced = result.layers.l1.kpis.find(k => k.version === 'v2.3')!.ks;
    // factor = 0.88 so KS should be lower
    expect(sliced).toBeLessThan(original);
  });

  it('approval_rate stays within [0, 1] after slice', () => {
    const slices = [
      { slice_dim: 'channel', slice_value: 'app' },
      { slice_dim: 'age_band', slice_value: '36-45' },
      { slice_dim: 'vintage', slice_value: '2023-11' },
    ];
    slices.forEach(slice => {
      const result = applyMockSlice(MOCK_RUN_RESULT, slice);
      result.layers.l2.kpis.forEach(k => {
        expect(k.approval_rate).toBeGreaterThanOrEqual(0);
        expect(k.approval_rate).toBeLessThanOrEqual(1);
      });
    });
  });

  it('young age band (18-25) reduces KS (factor=0.85)', () => {
    const original = MOCK_RUN_RESULT.layers.l1.kpis.find(k => k.version === 'v2.3')!.ks;
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'age_band', slice_value: '18-25' });
    const sliced = result.layers.l1.kpis.find(k => k.version === 'v2.3')!.ks;
    expect(sliced).toBeLessThan(original);
  });

  it('adjusts all 3 strategy KPIs consistently', () => {
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'online' });
    const versions = ['v2.3', 'v2.2', 'v2.4-Beta'];
    versions.forEach(v => {
      const orig = MOCK_RUN_RESULT.layers.l1.kpis.find(k => k.version === v)!;
      const sliced = result.layers.l1.kpis.find(k => k.version === v)!;
      expect(sliced.ks).not.toBe(orig.ks);
    });
  });

  it('preserves L4 matrices (not adjusted by slice)', () => {
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'online' });
    expect(result.layers.l4).toStrictEqual(MOCK_RUN_RESULT.layers.l4);
  });

  it('preserves L5 data (not adjusted by slice)', () => {
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'online' });
    expect(result.layers.l5).toStrictEqual(MOCK_RUN_RESULT.layers.l5);
  });

  it('handles unknown slice values gracefully (factor=1.0)', () => {
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'unknown_value' });
    const orig = MOCK_RUN_RESULT.layers.l1.kpis.find(k => k.version === 'v2.3')!.ks;
    const sliced = result.layers.l1.kpis.find(k => k.version === 'v2.3')!.ks;
    // factor defaults to 1.0, so KS should be same
    expect(sliced).toBeCloseTo(orig, 5);
  });

  it('L3 bad rates are higher when factor < 1', () => {
    const original = MOCK_RUN_RESULT.layers.l3.kpis.find(k => k.version === 'v2.3')!.m12_bad;
    const result = applyMockSlice(MOCK_RUN_RESULT, { slice_dim: 'channel', slice_value: 'offline' });
    const sliced = result.layers.l3.kpis.find(k => k.version === 'v2.3')!.m12_bad;
    // factor=0.88, so bad rate = orig * (2 - 0.88) = orig * 1.12, higher
    expect(sliced).toBeGreaterThan(original);
  });
});
