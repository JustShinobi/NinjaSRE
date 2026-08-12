import { describe, expect, it } from 'vitest';

import {
  UNPLACED,
  byZone,
  criticalityOf,
  criticalityRank,
  zoneOf,
} from '@/surfaces/screens/resources-view';

/**
 * The estate answers "what am I responsible for". Until the declared inventory
 * was wired, every resource answered it the same way — no zone, no criticality —
 * so the screen could only offer kind and state, which is what a hypervisor
 * knows rather than what an operator cares about.
 *
 * Both facts live in `attributes`: the zone is derived from the address, the
 * criticality is declared in the operator's own inventory. Neither is on every
 * resource, and the screen has to stay honest about that — a node is not
 * "unplaced" because somebody forgot it, it is a host and the inventory
 * describes guests.
 */

function resource(attributes: Record<string, unknown>): unknown {
  return { resource_id: 'res-a', attributes };
}

describe('reading the estate’s own vocabulary', () => {
  it('reads a zone off the attributes the sweep annotated', () => {
    expect(zoneOf(resource({ zone: 'dmz' }))).toBe('dmz');
  });

  it('reports a resource with no zone as unplaced rather than blank', () => {
    // A blank cell reads as "nobody knows"; the estate does know — nothing
    // placed it, because no declared network covers its address.
    expect(zoneOf(resource({}))).toBe(UNPLACED);
  });

  it('reads a criticality the operator declared', () => {
    expect(criticalityOf(resource({ criticality: 'high' }))).toBe('high');
  });

  it('leaves a resource nobody graded ungraded rather than inventing a middle', () => {
    // Defaulting to "medium" would rank fifty-five untouched resources against
    // each other on a value nobody wrote.
    expect(criticalityOf(resource({}))).toBe('');
  });
});

describe('ordering by how much a thing matters', () => {
  it('ranks a declared criticality above one nobody declared', () => {
    expect(criticalityRank(resource({ criticality: 'high' }))).toBeLessThan(
      criticalityRank(resource({})),
    );
  });

  it('ranks high above medium above low', () => {
    const rank = (value: string) => criticalityRank(resource({ criticality: value }));

    expect(rank('high')).toBeLessThan(rank('medium'));
    expect(rank('medium')).toBeLessThan(rank('low'));
  });

  it('keeps a word it has not met rather than folding it into one it resembles', () => {
    // An operator's vocabulary is theirs. "business-critical" sorts after the
    // ones this knows and still shows the word they wrote.
    const unknown = criticalityRank(resource({ criticality: 'business-critical' }));

    expect(unknown).toBeGreaterThan(criticalityRank(resource({ criticality: 'low' })));
    expect(criticalityOf(resource({ criticality: 'business-critical' }))).toBe(
      'business-critical',
    );
  });
});

describe('grouping the estate the way somebody reads it', () => {
  it('gathers resources under the zone they sit in', () => {
    const grouped = byZone([
      resource({ zone: 'apps' }),
      resource({ zone: 'dmz' }),
      resource({ zone: 'apps' }),
    ]);

    expect(grouped.map(([zone, rows]) => [zone, rows.length])).toEqual([
      ['apps', 2],
      ['dmz', 1],
    ]);
  });

  it('puts the unplaced last, whatever it would sort as alphabetically', () => {
    // Alphabetically "unplaced" lands in the middle, and the rows nobody placed
    // are the least useful thing to open the screen with.
    const grouped = byZone([resource({}), resource({ zone: 'vk8s' })]);

    expect(grouped.map(([zone]) => zone)).toEqual(['vk8s', UNPLACED]);
  });

  it('returns nothing for an estate with nothing in it', () => {
    expect(byZone([])).toEqual([]);
  });
});
