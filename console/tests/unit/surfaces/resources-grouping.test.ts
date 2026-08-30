import { describe, expect, it } from 'vitest';

import {
  groupByNode,
  healthSegments,
  unhealthySynthesis,
} from '@/surfaces/screens/resources-grouping';

function resource(overrides: Record<string, unknown> = {}): unknown {
  return {
    resource_id: 'r-1',
    display_name: 'r-1',
    kind: 'container',
    health: 'healthy',
    parent_id: null,
    parent_name: '',
    unhealthy_since: null,
    last_seen_at: '2026-08-26T12:00:00Z',
    ...overrides,
  };
}

describe('healthSegments', () => {
  it('orders healthy, unknown, unhealthy, absent, with a role and a count each', () => {
    const segments = healthSegments({ healthy: 71, unknown: 14, unhealthy: 14, absent: 12 });
    expect(segments.map((segment) => segment.health)).toEqual([
      'healthy',
      'unknown',
      'unhealthy',
      'absent',
    ]);
    expect(segments.every((segment) => segment.count > 0)).toBe(true);
  });

  it('drops a health value with zero count rather than drawing an empty segment', () => {
    const segments = healthSegments({ healthy: 5, degraded: 0 });
    expect(segments.map((segment) => segment.health)).toEqual(['healthy']);
  });
});

describe('groupByNode', () => {
  it('groups resources under their parent node name, unhealthy sections first', () => {
    const groups = groupByNode([
      resource({ resource_id: 'a', parent_id: 'n1', parent_name: 'pve01', health: 'healthy' }),
      resource({ resource_id: 'b', parent_id: 'n2', parent_name: 'pve02', health: 'unhealthy' }),
      resource({ resource_id: 'c', parent_id: 'n2', parent_name: 'pve02', health: 'healthy' }),
    ]);
    expect(groups.map((group) => group.nodeName)).toEqual(['pve02', 'pve01']);
    expect(groups[0]?.hasUnhealthy).toBe(true);
    expect(groups[1]?.hasUnhealthy).toBe(false);
  });

  it('sorts unhealthy resources before healthy ones inside a section', () => {
    const groups = groupByNode([
      resource({ resource_id: 'a', parent_id: 'n1', parent_name: 'pve01', health: 'healthy' }),
      resource({ resource_id: 'b', parent_id: 'n1', parent_name: 'pve01', health: 'unhealthy' }),
    ]);
    expect(groups[0]?.resources.map((entry) => (entry as { resource_id: string }).resource_id)).toEqual([
      'b',
      'a',
    ]);
  });

  it('groups a resource with no known parent under "no node declared"', () => {
    const groups = groupByNode([resource({ resource_id: 'a', parent_id: null })]);
    expect(groups[0]?.nodeId).toBe('');
  });
});

describe('unhealthySynthesis', () => {
  it('groups 3+ unhealthy resources sharing a node, kind and a 30-minute window', () => {
    const result = unhealthySynthesis([
      resource({
        resource_id: 'a',
        kind: 'container',
        parent_id: 'n1',
        parent_name: 'pve02',
        health: 'unhealthy',
        unhealthy_since: '2026-08-26T10:00:00Z',
      }),
      resource({
        resource_id: 'b',
        kind: 'container',
        parent_id: 'n1',
        parent_name: 'pve02',
        health: 'unhealthy',
        unhealthy_since: '2026-08-26T10:05:00Z',
      }),
      resource({
        resource_id: 'c',
        kind: 'container',
        parent_id: 'n1',
        parent_name: 'pve02',
        health: 'unhealthy',
        unhealthy_since: '2026-08-26T10:10:00Z',
      }),
    ]);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ nodeName: 'pve02', kind: 'container', count: 3 });
    expect(result[0]?.since).toBe('2026-08-26T10:00:00Z');
  });

  it('is empty with fewer than three in the same window', () => {
    const result = unhealthySynthesis([
      resource({ resource_id: 'a', health: 'unhealthy', parent_id: 'n1', unhealthy_since: '2026-08-26T10:00:00Z' }),
      resource({ resource_id: 'b', health: 'unhealthy', parent_id: 'n1', unhealthy_since: '2026-08-26T10:05:00Z' }),
    ]);
    expect(result).toEqual([]);
  });

  it('does not group unhealthy resources of different kinds together', () => {
    const result = unhealthySynthesis([
      resource({ resource_id: 'a', kind: 'container', parent_id: 'n1', health: 'unhealthy', unhealthy_since: '2026-08-26T10:00:00Z' }),
      resource({ resource_id: 'b', kind: 'virtual-machine', parent_id: 'n1', health: 'unhealthy', unhealthy_since: '2026-08-26T10:01:00Z' }),
      resource({ resource_id: 'c', kind: 'container', parent_id: 'n1', health: 'unhealthy', unhealthy_since: '2026-08-26T10:02:00Z' }),
    ]);
    expect(result).toEqual([]);
  });
});
