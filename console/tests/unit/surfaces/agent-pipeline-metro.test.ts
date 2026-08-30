import { describe, expect, it } from 'vitest';

import { stageRegime, toolSummary } from '@/surfaces/screens/agent-pipeline-metro';

describe('stageRegime', () => {
  it('names the bound model role when one is set', () => {
    expect(stageRegime('intake', 'intake')).toBe('model: intake');
  });

  it('says "no model" when nothing is bound and the stage is not the plan stage', () => {
    expect(stageRegime('resolve_integrations', '')).toBe('no model');
  });

  it('says "deterministic" for the plan stage specifically, with no model role', () => {
    expect(stageRegime('plan_evidence', '')).toBe('deterministic');
  });
});

describe('toolSummary', () => {
  const rows = [
    { known: true, available: true, sideEffect: 'read' },
    { known: true, available: true, sideEffect: 'read_sensitive' },
    { known: true, available: true, sideEffect: 'write_reversible' },
    { known: true, available: true, sideEffect: 'write_irreversible' },
    { known: true, available: false, sideEffect: 'write_irreversible' },
    { known: true, available: true, sideEffect: 'destructive' },
  ];

  it('counts enabled tools into three buckets: read, write-reversible, destructive', () => {
    const summary = toolSummary(rows);
    // read + read_sensitive fold into "read"; write_irreversible +
    // destructive fold into "destructive" -- only enabled (known &&
    // available) tools count, matching "X of Y enabled".
    expect(summary.read).toBe(2);
    expect(summary.writeReversible).toBe(1);
    // Two count as destructive: the enabled write_irreversible row and the
    // destructive row. The other write_irreversible row is disabled
    // (known but not available) and does not count anywhere.
    expect(summary.destructive).toBe(2);
    expect(summary.enabled).toBe(5);
  });

  it('is all zero with no rows', () => {
    const summary = toolSummary([]);
    expect(summary).toEqual({
      read: 0,
      writeReversible: 0,
      destructive: 0,
      enabled: 0,
    });
  });
});
