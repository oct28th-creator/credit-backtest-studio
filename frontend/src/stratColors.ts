export const STRAT_CLR: Record<string, string> = {
  'v2.2': '#64748b',      // champion gray
  'v2.3': '#2f4cdd',      // challenger blue
  'v2.4-Beta': '#ea580c', // beta orange
  'v2.5-RC': '#7c3aed',   // RC purple
};

export const C = (id: string): string => STRAT_CLR[id] || '#9ca3af';
