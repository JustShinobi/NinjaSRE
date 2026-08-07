import { describe, expect, it } from 'vitest';

import { isRunStatus, isSettled, roleFor, ROLES, RUN_STATUSES } from '@/lib/status';

describe('the status-to-role mapping', () => {
  it('gives every declared status a declared role', () => {
    for (const status of RUN_STATUSES) {
      expect(ROLES).toContain(roleFor(status));
    }
  });

  it('renders a failure as danger and a success as success', () => {
    expect(roleFor('failed')).toBe('danger');
    expect(roleFor('succeeded')).toBe('success');
  });

  it('renders a status it has never heard of as neutral rather than blanking', () => {
    // A gateway one version ahead of the console must not empty a screen.
    expect(roleFor('quiesced')).toBe('neutral');
    expect(isRunStatus('quiesced')).toBe(false);
  });

  it('recognises the statuses the gateway reports', () => {
    for (const status of RUN_STATUSES) {
      expect(isRunStatus(status)).toBe(true);
    }
  });

  it('settles only the three statuses that will not change again', () => {
    const settled = RUN_STATUSES.filter((status) => isSettled(status));
    expect(settled).toEqual(['succeeded', 'failed', 'cancelled']);
  });
});
