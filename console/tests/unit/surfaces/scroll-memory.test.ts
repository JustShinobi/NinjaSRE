import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  captureScrollPosition,
  consumeScrollPosition,
  peekScrollPosition,
} from '@/surfaces/scroll-memory';

/**
 * Where the catalogue was scrolled to, across the round trip through a panel.
 *
 * The module makes three promises that are easy to write and easy to break,
 * and each of them is a defect somebody would report as "the page jumps":
 *
 * - the position is read *twice* in one round trip, so peeking must not
 *   forget it and consuming must;
 * - a stale capture is not evidence about the navigation happening now, so a
 *   deep link does not land at a stranger's old offset;
 * - storage that refuses is a lost scroll position, never a broken
 *   navigation.
 *
 * The clock is faked rather than waited on: the age rule is five seconds, and
 * a suite that slept through it would be five seconds slower for every run in
 * order to prove one comparison.
 */

const KEY = 'ninjasre.integrations.scroll';

beforeEach(() => {
  sessionStorage.clear();
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-08-21T12:00:00Z'));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

describe('remembering where the catalogue was', () => {
  it('reads back the offset the page was left at', () => {
    window.scrollY = 640;

    captureScrollPosition();

    expect(peekScrollPosition()).toBe(640);
  });

  it('peeks without forgetting, so the second read still sees it', () => {
    window.scrollY = 320;
    captureScrollPosition();

    expect(peekScrollPosition()).toBe(320);
    expect(peekScrollPosition()).toBe(320);
  });

  it('forgets on consume, so an unrelated visit starts at the top', () => {
    window.scrollY = 200;
    captureScrollPosition();

    expect(consumeScrollPosition()).toBe(200);
    expect(peekScrollPosition()).toBeNull();
    expect(consumeScrollPosition()).toBeNull();
  });

  it('reports nothing when nothing was ever captured', () => {
    expect(peekScrollPosition()).toBeNull();
    expect(consumeScrollPosition()).toBeNull();
  });
});

describe('what a capture is no longer evidence of', () => {
  it('refuses a capture older than the navigation it would explain', () => {
    window.scrollY = 900;
    captureScrollPosition();

    vi.advanceTimersByTime(5001);

    expect(peekScrollPosition()).toBeNull();
  });

  it('still trusts one inside the window', () => {
    window.scrollY = 900;
    captureScrollPosition();

    vi.advanceTimersByTime(4999);

    expect(peekScrollPosition()).toBe(900);
  });
});

describe('what is not a position this module wrote', () => {
  it('reads nothing out of a value that is not JSON', () => {
    sessionStorage.setItem(KEY, 'not json at all');

    expect(peekScrollPosition()).toBeNull();
  });

  it('reads nothing out of a record with no offset in it', () => {
    sessionStorage.setItem(KEY, JSON.stringify({ at: Date.now() }));

    expect(peekScrollPosition()).toBeNull();
  });

  it('reads nothing out of a record with no timestamp in it', () => {
    sessionStorage.setItem(KEY, JSON.stringify({ y: 120 }));

    expect(peekScrollPosition()).toBeNull();
  });

  it('refuses an offset that is not a finite number', () => {
    sessionStorage.setItem(KEY, JSON.stringify({ y: 'halfway', at: Date.now() }));
    expect(peekScrollPosition()).toBeNull();

    sessionStorage.setItem(KEY, '{"y":null,"at":1}');
    expect(peekScrollPosition()).toBeNull();
  });

  it('refuses a timestamp that is not a finite number', () => {
    sessionStorage.setItem(KEY, JSON.stringify({ y: 120, at: 'earlier' }));

    expect(peekScrollPosition()).toBeNull();
  });

  it('reads nothing out of a bare value that is not a record', () => {
    sessionStorage.setItem(KEY, '42');

    expect(peekScrollPosition()).toBeNull();
  });
});

describe('storage that refuses', () => {
  it('loses the position rather than failing the navigation that left', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError');
    });

    expect(() => {
      captureScrollPosition();
    }).not.toThrow();
  });

  it('reads nothing rather than throwing at whoever asked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });

    expect(peekScrollPosition()).toBeNull();
  });

  it('still answers the caller when forgetting is what refuses', () => {
    window.scrollY = 480;
    captureScrollPosition();
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });

    expect(consumeScrollPosition()).toBe(480);
  });
});
