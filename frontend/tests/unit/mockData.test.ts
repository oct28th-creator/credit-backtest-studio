import { describe, it, expect } from 'vitest';
import { MOCK_RUN_RESULT, MOCK_STRATEGIES, MOCK_SAMPLES, STRAT_COLORS } from '../../src/data/mockData';

describe('MOCK_RUN_RESULT structure', () => {
  it('has required top-level fields', () => {
    expect(MOCK_RUN_RESULT).toHaveProperty('run_id');
    expect(MOCK_RUN_RESULT).toHaveProperty('champion');
    expect(MOCK_RUN_RESULT).toHaveProperty('challenger');
    expect(MOCK_RUN_RESULT).toHaveProperty('sample_size');
    expect(MOCK_RUN_RESULT).toHaveProperty('snapshot_sha');
    expect(MOCK_RUN_RESULT).toHaveProperty('layers');
  });

  it('has correct challenger and champion', () => {
    expect(MOCK_RUN_RESULT.challenger).toBe('v2.3');
    expect(MOCK_RUN_RESULT.champion).toBe('v2.2');
    expect(MOCK_RUN_RESULT.beta).toBe('v2.4-Beta');
  });

  it('has sample_size > 0', () => {
    expect(MOCK_RUN_RESULT.sample_size).toBeGreaterThan(0);
  });

  it('has all 5 layers', () => {
    const { layers } = MOCK_RUN_RESULT;
    expect(layers).toHaveProperty('l1');
    expect(layers).toHaveProperty('l2');
    expect(layers).toHaveProperty('l3');
    expect(layers).toHaveProperty('l4');
    expect(layers).toHaveProperty('l5');
  });
});

describe('L1 KPI values', () => {
  const l1 = MOCK_RUN_RESULT.layers.l1;

  it('has v2.3 KS=0.48 and AUC=0.83', () => {
    const v23 = l1.kpis.find(k => k.version === 'v2.3');
    expect(v23).toBeDefined();
    expect(v23!.ks).toBeCloseTo(0.48, 2);
    expect(v23!.auc).toBeCloseTo(0.83, 2);
  });

  it('has v2.2 KS=0.42 and AUC=0.78', () => {
    const v22 = l1.kpis.find(k => k.version === 'v2.2');
    expect(v22).toBeDefined();
    expect(v22!.ks).toBeCloseTo(0.42, 2);
    expect(v22!.auc).toBeCloseTo(0.78, 2);
  });

  it('has v2.4-Beta KS=0.43 and AUC=0.79', () => {
    const v24 = l1.kpis.find(k => k.version === 'v2.4-Beta');
    expect(v24).toBeDefined();
    expect(v24!.ks).toBeCloseTo(0.43, 2);
    expect(v24!.auc).toBeCloseTo(0.79, 2);
  });

  it('has PSI monthly data (6 months)', () => {
    expect(l1.psi_monthly).toHaveLength(6);
    l1.psi_monthly.forEach(p => {
      expect(p).toHaveProperty('month');
      expect(p).toHaveProperty('psi');
      expect(p).toHaveProperty('tone');
    });
  });

  it('has ROC data for all 3 strategies', () => {
    expect(l1.roc).toHaveProperty('v2.3');
    expect(l1.roc).toHaveProperty('v2.2');
    expect(l1.roc).toHaveProperty('v2.4-Beta');
  });

  it('ROC curves start at (0,0) and end at (1,1)', () => {
    const v23roc = l1.roc['v2.3'];
    expect(v23roc[0]).toEqual({ fpr: 0, tpr: 0 });
    expect(v23roc[v23roc.length - 1]).toEqual({ fpr: 1, tpr: 1 });
  });

  it('has CSI data', () => {
    expect(l1.csi.length).toBeGreaterThan(0);
    l1.csi.forEach(c => {
      expect(c).toHaveProperty('feature');
      expect(c).toHaveProperty('csi');
      expect(c.csi).toBeGreaterThanOrEqual(0);
    });
  });
});

describe('L2 KPI values', () => {
  const l2 = MOCK_RUN_RESULT.layers.l2;

  it('has v2.3 approval_rate=38% and RAROC=22%', () => {
    const v23 = l2.kpis.find(k => k.version === 'v2.3');
    expect(v23!.approval_rate).toBeCloseTo(0.38, 2);
    expect(v23!.raroc).toBeCloseTo(0.22, 2);
  });

  it('has v2.2 approval_rate=28% and RAROC=18%', () => {
    const v22 = l2.kpis.find(k => k.version === 'v2.2');
    expect(v22!.approval_rate).toBeCloseTo(0.28, 2);
    expect(v22!.raroc).toBeCloseTo(0.18, 2);
  });

  it('has v2.4-Beta approval_rate=45% and RAROC=16%', () => {
    const v24 = l2.kpis.find(k => k.version === 'v2.4-Beta');
    expect(v24!.approval_rate).toBeCloseTo(0.45, 2);
    expect(v24!.raroc).toBeCloseTo(0.16, 2);
  });

  it('has frontier data', () => {
    expect(l2.frontier.length).toBeGreaterThan(0);
  });
});

describe('L3 KPI values', () => {
  const l3 = MOCK_RUN_RESULT.layers.l3;

  it('has v2.3 m12_bad=2.4%', () => {
    const v23 = l3.kpis.find(k => k.version === 'v2.3');
    expect(v23!.m12_bad).toBeCloseTo(0.024, 3);
  });

  it('has v2.2 m12_bad=1.8%', () => {
    const v22 = l3.kpis.find(k => k.version === 'v2.2');
    expect(v22!.m12_bad).toBeCloseTo(0.018, 3);
  });

  it('has v2.4-Beta m12_bad=3.2%', () => {
    const v24 = l3.kpis.find(k => k.version === 'v2.4-Beta');
    expect(v24!.m12_bad).toBeCloseTo(0.032, 3);
  });
});

describe('L4 Swap Matrix', () => {
  const l4 = MOCK_RUN_RESULT.layers.l4;

  it('has v2.3_vs_v2.2 matrix', () => {
    expect(l4.matrices).toHaveProperty('v2.3_vs_v2.2');
  });

  it('v2.3 consistency=96.5%', () => {
    const m = l4.matrices['v2.3_vs_v2.2'];
    expect(m.consistency).toBeCloseTo(0.965, 3);
  });

  it('has swap_in=3240 and swap_out=2610', () => {
    const m = l4.matrices['v2.3_vs_v2.2'];
    expect(m.swap_in.count).toBe(3240);
    expect(m.swap_out.count).toBe(2610);
  });

  it('double_reject has null bad_rate', () => {
    const m = l4.matrices['v2.3_vs_v2.2'];
    expect(m.double_reject.bad_rate).toBeNull();
  });
});

describe('L5 Fairness values', () => {
  const l5 = MOCK_RUN_RESULT.layers.l5;

  it('v2.4-Beta young_core DI=0.77 (below 0.80)', () => {
    const v24Groups = l5.di_by_group['v2.4-Beta'];
    expect(v24Groups.young_core).toBeCloseTo(0.77, 2);
    expect(v24Groups.young_core).toBeLessThan(0.80);
  });

  it('v2.3 DI values are all >= 0.80', () => {
    const v23Groups = l5.di_by_group['v2.3'];
    expect(v23Groups.female_male).toBeGreaterThanOrEqual(0.80);
    expect(v23Groups.outsider_local).toBeGreaterThanOrEqual(0.80);
    expect(v23Groups.young_core).toBeGreaterThanOrEqual(0.80);
  });

  it('v2.2 DI values are all >= 0.90', () => {
    const v22Groups = l5.di_by_group['v2.2'];
    expect(v22Groups.female_male).toBeGreaterThanOrEqual(0.90);
    expect(v22Groups.outsider_local).toBeGreaterThanOrEqual(0.90);
    expect(v22Groups.young_core).toBeGreaterThanOrEqual(0.90);
  });

  it('has SHAP data for all strategies', () => {
    expect(l5.shap).toHaveProperty('v2.3');
    expect(l5.shap).toHaveProperty('v2.2');
    expect(l5.shap).toHaveProperty('v2.4-Beta');
    expect(l5.shap['v2.3'].length).toBeGreaterThan(0);
  });
});

describe('MOCK_STRATEGIES', () => {
  it('has 4 strategies', () => {
    expect(MOCK_STRATEGIES).toHaveLength(4);
  });

  it('has one challenger (v2.3)', () => {
    const challengers = MOCK_STRATEGIES.filter(s => s.role === 'challenger');
    expect(challengers).toHaveLength(1);
    expect(challengers[0].id).toBe('v2.3');
  });

  it('has one champion (v2.2)', () => {
    const champions = MOCK_STRATEGIES.filter(s => s.role === 'champion');
    expect(champions).toHaveLength(1);
    expect(champions[0].id).toBe('v2.2');
  });

  it('each strategy has rules with all sections', () => {
    MOCK_STRATEGIES.forEach(s => {
      expect(s.rules).toHaveProperty('anti_fraud_rules');
      expect(s.rules).toHaveProperty('if_else');
      expect(s.rules).toHaveProperty('scorecard_features');
      expect(s.rules).toHaveProperty('decision_table');
      expect(s.rules).toHaveProperty('bifurcation');
    });
  });
});

describe('MOCK_SAMPLES', () => {
  it('has 2 samples', () => {
    expect(MOCK_SAMPLES).toHaveLength(2);
  });

  it('each sample has required fields', () => {
    MOCK_SAMPLES.forEach(s => {
      expect(s).toHaveProperty('id');
      expect(s).toHaveProperty('name_zh');
      expect(s).toHaveProperty('name_en');
      expect(s.n_rows).toBeGreaterThan(0);
    });
  });
});

describe('STRAT_COLORS', () => {
  it('has all 4 strategy color entries', () => {
    expect(STRAT_COLORS).toHaveProperty('v2.2');
    expect(STRAT_COLORS).toHaveProperty('v2.3');
    expect(STRAT_COLORS).toHaveProperty('v2.4-Beta');
    expect(STRAT_COLORS).toHaveProperty('v2.5-RC');
  });

  it('challenger v2.3 is teal #1f5d6d', () => {
    expect(STRAT_COLORS['v2.3']).toBe('#1f5d6d');
  });

  it('champion v2.2 is taupe #7a6a55', () => {
    expect(STRAT_COLORS['v2.2']).toBe('#7a6a55');
  });
});
