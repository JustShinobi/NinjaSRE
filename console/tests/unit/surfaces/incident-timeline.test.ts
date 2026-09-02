import { describe, expect, it } from 'vitest';

import { positionOnTimeline } from '@/surfaces/incident-timeline';
import type { IncidentOccurrence } from '@/surfaces/incident-groups';

const NOW = new Date('2026-08-26T12:00:00Z');

function occurrence(overrides: Partial<IncidentOccurrence> = {}): IncidentOccurrence {
  return {
    id: 'inc-1',
    publicId: 'inc_abc',
    summary: '',
    state: 'resolved',
    severity: 'critical',
    at: '2026-08-26T06:00:00Z',
    runId: '',
    ...overrides,
  };
}

describe('positionOnTimeline', () => {
  it('places one point per occurrence inside the 24h window, proportional to its age', () => {
    const result = positionOnTimeline(
      [
        occurrence({ id: 'a', at: '2026-08-25T12:00:00Z' }), // window start, left edge
        occurrence({ id: 'b', at: '2026-08-26T12:00:00Z' }), // now, right edge
      ],
      NOW,
    );
    expect(result.points).toHaveLength(2);
    const byId = new Map(result.points.map((point) => [point.id, point]));
    expect(byId.get('a')?.percent).toBeCloseTo(0, 1);
    expect(byId.get('b')?.percent).toBeCloseTo(100, 1);
    expect(result.overflowCount).toBe(0);
  });

  it('never repeats an occurrence as a second point', () => {
    const occurrences = [occurrence({ id: 'a' }), occurrence({ id: 'b' })];
    const result = positionOnTimeline(occurrences, NOW);
    expect(new Set(result.points.map((point) => point.id)).size).toBe(2);
  });

  it('counts an occurrence older than the window as overflow rather than hiding it', () => {
    const result = positionOnTimeline(
      [
        occurrence({ id: 'old', at: '2026-08-24T00:00:00Z' }),
        occurrence({ id: 'recent', at: '2026-08-26T10:00:00Z' }),
      ],
      NOW,
    );
    expect(result.points.map((point) => point.id)).toEqual(['recent']);
    expect(result.overflowCount).toBe(1);
  });

  it('marks a terminal occurrence with a circle and a live one with a diamond', () => {
    const result = positionOnTimeline(
      [
        occurrence({ id: 'done', state: 'resolved', at: '2026-08-26T10:00:00Z' }),
        occurrence({ id: 'live', state: 'investigating', at: '2026-08-26T11:00:00Z' }),
      ],
      NOW,
    );
    const byId = new Map(result.points.map((point) => [point.id, point]));
    expect(byId.get('done')?.shape).toBe('circle');
    expect(byId.get('live')?.shape).toBe('diamond');
  });

  it('a single occurrence needs no strip at all', () => {
    expect(positionOnTimeline([occurrence()], NOW).points).toHaveLength(0);
  });

  it('an empty occurrence list needs no strip', () => {
    const result = positionOnTimeline([], NOW);
    expect(result.points).toHaveLength(0);
    expect(result.overflowCount).toBe(0);
  });

  it('honours a caller-supplied window instead of the 24h default', () => {
    // 30 hours old: inside a 48h window, outside the default 24h one.
    const result = positionOnTimeline(
      [
        occurrence({ id: 'a', at: '2026-08-26T06:00:00Z' }), // 6h old, inside both
        occurrence({ id: 'b', at: '2026-08-25T06:00:00Z' }), // 30h old
      ],
      NOW,
      48,
    );

    expect(result.points.map((point) => point.id)).toEqual(['a', 'b']);
    expect(result.overflowCount).toBe(0);
  });
});
