import { describe, expect, it } from 'vitest';

import {
  STAGE_TREATMENT_CLASSES,
  stageRegime,
  stageTreatment,
  toolSummary,
} from '@/surfaces/screens/agent-pipeline-metro';

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

describe('stageTreatment', () => {
  const order = [
    'resolve_integrations',
    'intake',
    'plan_evidence',
    'gather_evidence',
    'diagnose',
    'deliver',
  ];

  it('draws every stage not-reached when nothing names a current one', () => {
    for (const stage of order) {
      expect(stageTreatment(order, stage, undefined)).toBe('not-reached');
    }
  });

  it('draws the current stage as running', () => {
    expect(stageTreatment(order, 'gather_evidence', 'gather_evidence')).toBe('running');
  });

  it('draws every stage ahead of the current one as passed', () => {
    expect(stageTreatment(order, 'resolve_integrations', 'gather_evidence')).toBe(
      'passed',
    );
    expect(stageTreatment(order, 'intake', 'gather_evidence')).toBe('passed');
    expect(stageTreatment(order, 'plan_evidence', 'gather_evidence')).toBe('passed');
  });

  it('draws every stage behind the current one as not-reached', () => {
    expect(stageTreatment(order, 'diagnose', 'gather_evidence')).toBe('not-reached');
    expect(stageTreatment(order, 'deliver', 'gather_evidence')).toBe('not-reached');
  });

  it('falls back to not-reached when the current stage is not one this pipeline names', () => {
    expect(stageTreatment(order, 'intake', 'a_stage_this_order_does_not_have')).toBe(
      'not-reached',
    );
  });
});

describe('STAGE_TREATMENT_CLASSES', () => {
  it('rings a passed stage in the accent and grounds it on the success tint', () => {
    expect(STAGE_TREATMENT_CLASSES.passed).toContain('border-accent');
    expect(STAGE_TREATMENT_CLASSES.passed).toContain('bg-success-bg');
    expect(STAGE_TREATMENT_CLASSES.passed).toContain('text-accent');
  });

  it('fills the running stage solid with the accent and sets its icon in the on-accent contrast', () => {
    expect(STAGE_TREATMENT_CLASSES.running).toContain('bg-accent');
    // Filled, not tinted -- the passed and running treatments must not share
    // a ground, or a viewer could not tell "already ran" from "running now".
    expect(STAGE_TREATMENT_CLASSES.running).not.toContain('bg-accent-bg');
    expect(STAGE_TREATMENT_CLASSES.running).toContain('text-on-accent');
  });

  it('grounds a not-reached stage neutrally, ringed in the strong border, icon muted', () => {
    expect(STAGE_TREATMENT_CLASSES['not-reached']).toContain('border-border-strong');
    expect(STAGE_TREATMENT_CLASSES['not-reached']).toContain('bg-neutral-bg');
    expect(STAGE_TREATMENT_CLASSES['not-reached']).toContain('text-muted');
  });
});
