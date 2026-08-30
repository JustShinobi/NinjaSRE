import { describe, expect, it } from 'vitest';

import { degradedFindingsWithoutDetector } from '@/surfaces/screens/detector-coverage-gap';

describe('degradedFindingsWithoutDetector', () => {
  it('counts a degraded resource no current observation names', () => {
    const count = degradedFindingsWithoutDetector(
      [
        { resource_id: 'r-1', health: 'unhealthy' },
        { resource_id: 'r-2', health: 'degraded' },
        { resource_id: 'r-3', health: 'healthy' },
      ],
      [{ resource_id: 'r-1' }],
    );
    // r-1 is covered by an observation; r-2 is degraded and uncovered; r-3
    // is healthy and never counts regardless of coverage.
    expect(count).toBe(1);
  });

  it('is zero when every degraded resource has a current observation', () => {
    const count = degradedFindingsWithoutDetector(
      [{ resource_id: 'r-1', health: 'unhealthy' }],
      [{ resource_id: 'r-1' }],
    );
    expect(count).toBe(0);
  });

  it('is zero with no resources at all', () => {
    expect(degradedFindingsWithoutDetector([], [])).toBe(0);
  });
});
