import { describe, expect, it } from 'vitest';

import { groupBySubject } from '@/surfaces/incident-groups';

/**
 * Folding a repeating estate back into the problems it actually has.
 *
 * Staging serves fifty incidents. Seven conditions account for all of them:
 * `ProxmoxGuestStopped` nine times, `RedisExporterDown` nine, `InstanceDown`
 * eight, over half a day. Listed one per row they read as fifty unrelated
 * problems, which is both unusable and untrue — the second firing of one cause
 * is a recurrence, and the store knows it, because it carries the correlation
 * key it would have reopened the incident under.
 *
 * So the group key is that field and never the title. Two firings of one cause
 * share a key by construction; two unrelated incidents can share prose.
 */

/** One incident, in the shape the listing serves. */
function incident(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    incident_id: 'inc-1',
    public_id: 'one',
    correlation_key: 'detector:proxmox-guest-stopped:resource:lxc/122',
    title: 'ProxmoxGuestStopped',
    summary: 'A Proxmox guest that was running has stopped',
    state: 'resolved',
    severity: 'critical',
    detector: 'alertmanager',
    subjects: ['lxc/122'],
    opened_at: '2026-08-26T06:00:00.000Z',
    ...over,
  };
}

describe('groupBySubject', () => {
  it('folds repeated firings of one cause into one row', () => {
    const groups = groupBySubject([
      incident({ incident_id: 'a', opened_at: '2026-08-26T06:00:00.000Z' }),
      incident({ incident_id: 'b', opened_at: '2026-08-26T03:00:00.000Z' }),
      incident({ incident_id: 'c', opened_at: '2026-08-25T22:00:00.000Z' }),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.count).toBe(3);
    expect(groups[0]?.occurrences.map((one) => one.id)).toEqual(['a', 'b', 'c']);
  });

  it('groups by the key and never by the words', () => {
    // Two conditions on one resource write the same prose and are not the same
    // problem; one condition on two resources is not one problem either.
    const groups = groupBySubject([
      incident({ incident_id: 'a', correlation_key: 'detector:x:resource:lxc/122' }),
      incident({ incident_id: 'b', correlation_key: 'detector:y:resource:lxc/122' }),
    ]);

    expect(groups).toHaveLength(2);
  });

  it('carries an incident with no key as a group of its own', () => {
    // A deployment one version behind serves no key. Folding every one of them
    // together under the empty string would invent a problem nobody has.
    const groups = groupBySubject([
      incident({ incident_id: 'a', correlation_key: '' }),
      incident({ incident_id: 'b', correlation_key: '' }),
    ]);

    expect(groups).toHaveLength(2);
    expect(groups.every((group) => group.count === 1)).toBe(true);
  });

  it('says a group is live when anything under it still is', () => {
    const groups = groupBySubject([
      incident({ incident_id: 'a', state: 'resolved' }),
      incident({ incident_id: 'b', state: 'investigating' }),
      incident({ incident_id: 'c', state: 'suppressed' }),
    ]);

    expect(groups[0]?.live).toBe(true);
    expect(groups[0]?.state).toBe('investigating');
  });

  it('says a group has ended only when every firing under it has', () => {
    const groups = groupBySubject([
      incident({ incident_id: 'a', state: 'resolved' }),
      incident({ incident_id: 'b', state: 'suppressed' }),
    ]);

    expect(groups[0]?.live).toBe(false);
    // The newest firing's own state, rather than a word this console invents
    // to describe a set. `resolved` opened later, so `resolved` is what the
    // group reads as.
    expect(groups[0]?.state).toBe('resolved');
  });

  it('puts what is still happening above what is over', () => {
    const groups = groupBySubject([
      incident({
        incident_id: 'old-live',
        correlation_key: 'k-live',
        state: 'investigating',
        opened_at: '2026-08-20T00:00:00.000Z',
      }),
      incident({
        incident_id: 'new-done',
        correlation_key: 'k-done',
        state: 'resolved',
        opened_at: '2026-08-26T09:00:00.000Z',
      }),
    ]);

    // Recency loses to still-being-a-problem. A list sorted by time alone puts
    // this morning's closure above last week's outage, which is the ordering
    // that made the old screen unreadable.
    expect(groups.map((group) => group.key)).toEqual(['k-live', 'k-done']);
  });

  it('orders two live groups by severity before recency', () => {
    const groups = groupBySubject([
      incident({
        incident_id: 'a',
        correlation_key: 'k-high',
        severity: 'high',
        state: 'open',
        opened_at: '2026-08-26T09:00:00.000Z',
      }),
      incident({
        incident_id: 'b',
        correlation_key: 'k-critical',
        severity: 'critical',
        state: 'open',
        opened_at: '2026-08-26T01:00:00.000Z',
      }),
    ]);

    expect(groups.map((group) => group.key)).toEqual(['k-critical', 'k-high']);
  });

  it('reports the newest firing as the group instant', () => {
    const groups = groupBySubject([
      incident({ incident_id: 'a', opened_at: '2026-08-25T22:00:00.000Z' }),
      incident({ incident_id: 'b', opened_at: '2026-08-26T06:00:00.000Z' }),
    ]);

    expect(groups[0]?.lastAt).toBe('2026-08-26T06:00:00.000Z');
    expect(groups[0]?.firstAt).toBe('2026-08-25T22:00:00.000Z');
  });

  it('takes the worst severity anything under it fired at', () => {
    const groups = groupBySubject([
      incident({ incident_id: 'a', severity: 'low' }),
      incident({ incident_id: 'b', severity: 'critical' }),
      incident({ incident_id: 'c', severity: 'medium' }),
    ]);

    expect(groups[0]?.severity).toBe('critical');
  });

  it('names the subjects the firings landed on, without repeating one', () => {
    const groups = groupBySubject([
      incident({ incident_id: 'a', subjects: ['lxc/122', 'pve02'] }),
      incident({ incident_id: 'b', subjects: ['lxc/122'] }),
      incident({ incident_id: 'c', subjects: ['lxc/152'] }),
    ]);

    expect(groups[0]?.subjects).toEqual(['lxc/122', 'pve02', 'lxc/152']);
  });

  it('is empty for an empty listing rather than one empty group', () => {
    expect(groupBySubject([])).toEqual([]);
  });
});
