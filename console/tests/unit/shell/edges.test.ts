import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { formatDuration } from '@/i18n/format';
import { guard } from '@/session/guard';
import { SESSION_COOKIE } from '@/session/cookies';
import { loadAttention, loadGuardian, loadRecentRuns } from '@/shell/load';
import { trailFor, areaFor } from '@/shell/routes';

/**
 * The branches nothing normal takes.
 *
 * Each of these is a path that only runs when something has already gone wrong,
 * which is exactly why they are worth a test: they are the code nobody watches
 * and the code that decides what a bad day looks like.
 */

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('a failure the shell has no answer for', () => {
  it('is re-raised rather than swallowed into an empty panel', async () => {
    // A refused read and an unreachable deployment are both things a panel can
    // say. A programming error is not, and turning one into an empty list is
    // how a defect ships looking like a quiet afternoon.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new RangeError('a defect, not a network'))),
    );

    await expect(loadRecentRuns('opaque')).rejects.toThrow(RangeError);
    await expect(loadAttention('opaque')).rejects.toThrow(RangeError);
    await expect(loadGuardian('opaque')).rejects.toThrow(RangeError);
  });
});

describe('a read that never comes back', () => {
  it('gives the frame its empty answer rather than holding the page', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    const waiting = loadAttention('opaque');
    const runs = loadRecentRuns('opaque');
    const guardian = loadGuardian('opaque');
    await vi.advanceTimersByTimeAsync(5000);

    expect(await waiting).toEqual([]);
    expect(await runs).toEqual([]);
    // Silent rather than acting, which is the one direction this must never be
    // wrong in.
    expect(await guardian).toEqual({ live: false, posture: 'propose' });
    vi.useRealTimers();
  });
});

describe('a duration longer than an afternoon', () => {
  it('is days and hours, and stops there', () => {
    expect(formatDuration('en', 2 * 86400 + 3 * 3600 + 4 * 60 + 5)).toBe('2d 3h');
    expect(formatDuration('en', 86400)).toBe('1d');
    expect(formatDuration('en', 3600)).toBe('1h');
  });
});

describe('a trail with a step in the middle', () => {
  it('links every crumb but the one you are standing on', () => {
    const trail = trailFor(areaFor('runs'), [
      { label: 'run-0001', href: '/runs/run-0001' },
      { label: 'Evidence' },
    ]);

    expect(trail.map((crumb) => crumb.href)).toEqual([
      '/runs',
      '/runs/run-0001',
      undefined,
    ]);
    expect(trail.map((crumb) => crumb.translate)).toEqual([true, false, false]);
  });

  it('does not link a middle crumb that has nowhere to go', () => {
    const trail = trailFor(areaFor('runs'), [
      { label: 'run-0001' },
      { label: 'Evidence' },
    ]);
    expect(trail[1]?.href).toBeUndefined();
  });
});

describe('the guard and the paths beneath an exempt one', () => {
  it('lets the session route handler through under any sub-path', () => {
    expect(guard('/api/session/anything', '', new Map()).kind).toBe('allow');
  });

  it('does not let a path that merely starts with the same letters through', () => {
    expect(guard('/api/sessions-elsewhere', '', new Map()).kind).toBe('redirect');
  });

  it('lets a signed-in visitor reach a route nobody declared, so it can 404', () => {
    const signedIn = new Map([[SESSION_COOKIE, 'opaque']]);
    expect(guard('/no-such-area', '', signedIn).kind).toBe('allow');
  });
});
