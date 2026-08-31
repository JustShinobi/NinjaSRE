import { describe, expect, it } from 'vitest';

import {
  capNodeSection,
  groupByNode,
  healthSegments,
  unhealthySynthesis,
  type NodeGroup,
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
    const segments = healthSegments({
      healthy: 71,
      unknown: 14,
      unhealthy: 14,
      absent: 12,
    });
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
      resource({
        resource_id: 'a',
        parent_id: 'n1',
        parent_name: 'pve01',
        health: 'healthy',
      }),
      resource({
        resource_id: 'b',
        parent_id: 'n2',
        parent_name: 'pve02',
        health: 'unhealthy',
      }),
      resource({
        resource_id: 'c',
        parent_id: 'n2',
        parent_name: 'pve02',
        health: 'healthy',
      }),
    ]);
    expect(groups.map((group) => group.nodeName)).toEqual(['pve02', 'pve01']);
    expect(groups[0]?.hasUnhealthy).toBe(true);
    expect(groups[1]?.hasUnhealthy).toBe(false);
  });

  it('sorts unhealthy resources before healthy ones inside a section', () => {
    const groups = groupByNode([
      resource({
        resource_id: 'a',
        parent_id: 'n1',
        parent_name: 'pve01',
        health: 'healthy',
      }),
      resource({
        resource_id: 'b',
        parent_id: 'n1',
        parent_name: 'pve01',
        health: 'unhealthy',
      }),
    ]);
    expect(
      groups[0]?.resources.map(
        (entry) => (entry as { resource_id: string }).resource_id,
      ),
    ).toEqual(['b', 'a']);
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
      resource({
        resource_id: 'a',
        health: 'unhealthy',
        parent_id: 'n1',
        unhealthy_since: '2026-08-26T10:00:00Z',
      }),
      resource({
        resource_id: 'b',
        health: 'unhealthy',
        parent_id: 'n1',
        unhealthy_since: '2026-08-26T10:05:00Z',
      }),
    ]);
    expect(result).toEqual([]);
  });

  it('does not group unhealthy resources of different kinds together', () => {
    const result = unhealthySynthesis([
      resource({
        resource_id: 'a',
        kind: 'container',
        parent_id: 'n1',
        health: 'unhealthy',
        unhealthy_since: '2026-08-26T10:00:00Z',
      }),
      resource({
        resource_id: 'b',
        kind: 'virtual-machine',
        parent_id: 'n1',
        health: 'unhealthy',
        unhealthy_since: '2026-08-26T10:01:00Z',
      }),
      resource({
        resource_id: 'c',
        kind: 'container',
        parent_id: 'n1',
        health: 'unhealthy',
        unhealthy_since: '2026-08-26T10:02:00Z',
      }),
    ]);
    expect(result).toEqual([]);
  });
});

/** `count` resources on `n1`/pve02, half unhealthy when `unhealthy` is given. */
function nodeOf(count: number, unhealthy = 0): unknown[] {
  const made: unknown[] = [];
  for (let index = 0; index < count; index += 1) {
    made.push(
      resource({
        resource_id: `r-${String(index)}`,
        display_name: `r-${String(index)}`,
        parent_id: 'n1',
        parent_name: 'pve02',
        health: index < unhealthy ? 'unhealthy' : 'healthy',
      }),
    );
  }
  return made;
}

/** `resources` grouped and narrowed to its one section -- these fixtures always carry exactly one node. */
function firstSection(resources: readonly unknown[]): NodeGroup {
  const [section] = groupByNode(resources);
  if (section === undefined) {
    throw new Error('expected groupByNode to return at least one section');
  }
  return section;
}

describe('capNodeSection', () => {
  it('shows every resource of an all-healthy section at or under one row, no link', () => {
    const capped = capNodeSection(firstSection(nodeOf(4)));
    expect(capped.shown).toHaveLength(4);
    expect(capped.more).toBeUndefined();
  });

  it('shows every resource of a section with unhealthy ones at or under two rows, no link', () => {
    const capped = capNodeSection(firstSection(nodeOf(8, 2)));
    expect(capped.shown).toHaveLength(8);
    expect(capped.more).toBeUndefined();
  });

  it('caps an all-healthy section at one row and points at every resource on the node', () => {
    // pve01 in the board: 58 resources, none unhealthy -- one row (4) shown,
    // "see all 58 resources of pve01" rather than an unhealthy count of zero.
    const capped = capNodeSection(firstSection(nodeOf(58)));
    expect(capped.shown).toHaveLength(4);
    expect(capped.more).toEqual({ count: 58, onlyUnhealthy: false });
  });

  it('caps a section with unhealthy ones at two rows and names the unhealthy total when more are hidden', () => {
    // pve02 in the board: 41 resources, 14 unhealthy -- two rows (8, all
    // unhealthy since they sort first) shown, "see the 14 unhealthy of
    // pve02" rather than the node's whole resource count.
    const capped = capNodeSection(firstSection(nodeOf(41, 14)));
    expect(capped.shown).toHaveLength(8);
    expect(
      capped.shown.every(
        (entry) => (entry as { health: string }).health === 'unhealthy',
      ),
    ).toBe(true);
    expect(capped.more).toEqual({ count: 14, onlyUnhealthy: true });
  });

  it('points at every resource on the node, not the unhealthy count, once every unhealthy one already fits', () => {
    // Exactly a full two rows unhealthy, and nothing unhealthy left hidden:
    // the honest link is "see all", not "see the 8 unhealthy" -- there is
    // no additional unhealthy one waiting behind it.
    const capped = capNodeSection(firstSection(nodeOf(20, 8)));
    expect(capped.shown).toHaveLength(8);
    expect(capped.more).toEqual({ count: 20, onlyUnhealthy: false });
  });
});
