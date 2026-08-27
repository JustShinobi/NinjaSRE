import { describe, expect, it } from 'vitest';

import {
  delayAfter,
  freshnessOf,
  REFRESH_BACKOFF_MS,
  REFRESH_INTERVAL_MS,
  STALE_AFTER_FAILURES,
} from '@/live/freshness';

/**
 * What the frame is allowed to claim about how current it is.
 *
 * The complaint this answers is that an operator had to press reload to find
 * out whether anything had moved, on a console whose subject is a deployment
 * that changes while nobody is looking. The indicator that replaces the press
 * has exactly one way to be worse than nothing: saying the view is current
 * when it is not.
 */
describe('freshnessOf', () => {
  it('is live when the tab is watched and nothing has failed', () => {
    expect(freshnessOf({ visible: true, refreshing: false, failures: 0 })).toBe('live');
  });

  it('says so while a re-read is in flight', () => {
    expect(freshnessOf({ visible: true, refreshing: true, failures: 0 })).toBe(
      'refreshing',
    );
  });

  it('never claims to be current on a tab nobody is looking at', () => {
    // A hidden tab is not re-read, so whatever is on it is as old as the last
    // time it was. Coming back to a tab that says "live" over an hour-old page
    // is the specific way an indicator becomes a lie.
    expect(freshnessOf({ visible: false, refreshing: false, failures: 0 })).toBe(
      'paused',
    );
    expect(freshnessOf({ visible: false, refreshing: true, failures: 0 })).toBe(
      'paused',
    );
    expect(freshnessOf({ visible: false, refreshing: false, failures: 9 })).toBe(
      'paused',
    );
  });

  it('tolerates one failure without alarming anybody', () => {
    // The data on screen is still seconds old. A gateway hiccup is not an
    // outage, and an indicator that flips on every one is an indicator people
    // learn to ignore.
    expect(freshnessOf({ visible: true, refreshing: false, failures: 1 })).toBe('live');
  });

  it('stops claiming to be current once the gateway is plainly unreachable', () => {
    expect(
      freshnessOf({ visible: true, refreshing: false, failures: STALE_AFTER_FAILURES }),
    ).toBe('stale');
  });

  it('stays stale while it is retrying, rather than flickering back to fresh', () => {
    // An attempt in flight after three failures is still an attempt over data
    // nobody should trust yet.
    expect(
      freshnessOf({ visible: true, refreshing: true, failures: STALE_AFTER_FAILURES }),
    ).toBe('stale');
  });
});

describe('delayAfter', () => {
  it('uses the ordinary interval while everything is answering', () => {
    expect(delayAfter(0)).toBe(REFRESH_INTERVAL_MS);
  });

  it('waits longer after each consecutive failure', () => {
    expect(delayAfter(1)).toBe(REFRESH_BACKOFF_MS[0]);
    expect(delayAfter(2)).toBe(REFRESH_BACKOFF_MS[1]);
    expect(delayAfter(3)).toBe(REFRESH_BACKOFF_MS[2]);
  });

  it('stops growing rather than backing off without bound', () => {
    // An operator who has just fixed the gateway should not wait a quarter of
    // an hour for the console to notice.
    const last = REFRESH_BACKOFF_MS[REFRESH_BACKOFF_MS.length - 1];
    expect(delayAfter(40)).toBe(last);
    expect(delayAfter(400)).toBe(last);
  });

  it('never waits less than the ordinary interval', () => {
    // Backing off has to back *off*. A table that shortened under failure
    // would turn an unreachable gateway into a denial of service against it.
    for (const failures of [0, 1, 2, 3, 10]) {
      expect(delayAfter(failures)).toBeGreaterThanOrEqual(REFRESH_INTERVAL_MS);
    }
  });
});
