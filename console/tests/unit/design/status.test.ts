import { describe, expect, it } from 'vitest';

import { SEMANTIC_ROLES } from '@/design/tokens';
import {
  isRunStatus,
  isSettled,
  ATTENTION_STATUSES,
  RESOURCE_STATUSES,
  roleFor,
  RUN_STATUSES,
  SHAPES,
  statusPresentation,
} from '@/design/status';

/**
 * One mapping, so two screens cannot disagree.
 *
 * The property that matters most is the one for a status nobody has declared:
 * a gateway one version ahead of the console must not blank a screen, must not
 * claim an error, and must still say what it said. Neutral, with the raw text.
 */

describe('the status mapping', () => {
  it('gives every declared status a declared role', () => {
    for (const status of [
      ...RUN_STATUSES,
      ...RESOURCE_STATUSES,
      ...ATTENTION_STATUSES,
    ]) {
      expect(SEMANTIC_ROLES).toContain(roleFor(status));
    }
  });

  it('recognises every status a surface puts in a chip', () => {
    // The point of declaring them: a severity drawn as an unknown word is a
    // severity drawn in grey, which is the one colour it must not be.
    for (const status of ATTENTION_STATUSES) {
      expect(statusPresentation(status).known, status).toBe(true);
    }
  });

  it('tells two danger states apart by shape as well as by colour', () => {
    // Roughly one man in twelve cannot separate this palette's danger from its
    // warning; `critical` and `high` are both danger and must still differ.
    expect(statusPresentation('critical').shape).not.toBe(
      statusPresentation('high').shape,
    );
    expect(statusPresentation('irreversible').role).toBe('danger');
    expect(statusPresentation('read_only').role).toBe('success');
  });

  it('reads a failure as danger and a success as success', () => {
    expect(roleFor('failed')).toBe('danger');
    expect(roleFor('succeeded')).toBe('success');
    expect(roleFor('unhealthy')).toBe('danger');
    expect(roleFor('healthy')).toBe('success');
  });

  it('renders a status it has never heard of as neutral, with its own words', () => {
    const presented = statusPresentation('quiesced');

    expect(presented.role).toBe('neutral');
    expect(presented.label).toBe('quiesced');
    expect(presented.known).toBe(false);
    expect(isRunStatus('quiesced')).toBe(false);
  });

  it('never renders an unknown status as blank', () => {
    for (const nonsense of ['', '   ', 'a-status-from-the-future']) {
      expect(statusPresentation(nonsense).label.length).toBeGreaterThan(0);
    }
  });

  it('recognises the statuses the gateway reports', () => {
    for (const status of RUN_STATUSES) {
      expect(isRunStatus(status)).toBe(true);
    }
  });

  it('settles only the three statuses that will not change again', () => {
    expect(RUN_STATUSES.filter((status) => isSettled(status))).toEqual([
      'succeeded',
      'failed',
      'cancelled',
    ]);
  });
});

describe('shape, so colour is never the only carrier', () => {
  it('gives every status a shape as well as a role', () => {
    for (const status of [...RUN_STATUSES, ...RESOURCE_STATUSES, 'invented']) {
      expect(SHAPES).toContain(statusPresentation(status).shape);
    }
  });

  it('carries the documented shape for each documented state', () => {
    const shapeOf = (status: string): string => statusPresentation(status).shape;

    expect(shapeOf('healthy')).toBe('filled-circle');
    expect(shapeOf('degraded')).toBe('triangle');
    expect(shapeOf('unhealthy')).toBe('square');
    expect(shapeOf('unknown')).toBe('hollow-circle');
    expect(shapeOf('stale')).toBe('dimmed-circle');
    expect(shapeOf('maintenance')).toBe('rotated-square');
    expect(shapeOf('absent')).toBe('dash');
  });

  it('distinguishes the two states that share the neutral role by shape alone', () => {
    // Both are neutral; if they shared a shape too, a viewer who cannot
    // separate the hues would have nothing left to separate them by.
    expect(roleFor('unknown')).toBe('neutral');
    expect(roleFor('stale')).toBe('neutral');
    expect(statusPresentation('unknown').shape).not.toBe(
      statusPresentation('stale').shape,
    );
  });
});
