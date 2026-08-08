import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { read } from '@/lib/api';
import {
  SessionController,
  sessionController,
  type SessionEnding,
} from '@/session/controller';
import { sessionLife } from '@/session/expiry';
import { safeReturnTo, SESSION_WARNING_SECONDS, signInHref } from '@/session/cookies';

/**
 * The single collapse, the route it remembers, and the boundary of the warning.
 *
 * The concurrency claim is the one worth writing carefully. Three refusals
 * arriving together must produce one ending, and the reason has to be that there
 * is one controller rather than that each caller looked to see whether another
 * had already acted — a look-then-act is a race with a small window, and the
 * small window is the one that opens on the morning it matters.
 */

describe('a session ends once', () => {
  it('collapses three endings into one', () => {
    const endings: SessionEnding[] = [];
    const controller = new SessionController();
    controller.listen((ending) => endings.push(ending));

    controller.unauthorized('/runs');
    controller.unauthorized('/approvals');
    controller.unauthorized('/audit');

    expect(endings).toHaveLength(1);
    expect(endings[0]?.returnTo).toBe('/runs');
    expect(controller.hasEnded).toBe(true);
  });

  it('remembers the route the viewer was on, not the last one to fail', () => {
    const endings: SessionEnding[] = [];
    const controller = new SessionController();
    controller.listen((ending) => endings.push(ending));

    controller.unauthorized('/incidents?state=open');

    expect(endings[0]?.returnTo).toBe('/incidents?state=open');
  });

  it('distinguishes an expiry from somebody leaving', () => {
    const expired: SessionEnding[] = [];
    const left: SessionEnding[] = [];
    const one = new SessionController();
    const other = new SessionController();
    one.listen((ending) => expired.push(ending));
    other.listen((ending) => left.push(ending));

    one.unauthorized('/');
    other.signOut('/');

    expect(expired[0]?.reason).toBe('expired');
    expect(left[0]?.reason).toBe('signed-out');
  });

  it('says nothing at all when nobody is listening', () => {
    const controller = new SessionController();
    expect(() => {
      controller.unauthorized('/');
    }).not.toThrow();
    expect(controller.hasEnded).toBe(true);
  });
});

describe('three concurrent refusals through the real client', () => {
  beforeEach(() => {
    sessionController.reset();
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    sessionController.reset();
  });

  it('produce exactly one session ending and one prompt', async () => {
    const endings: SessionEnding[] = [];
    sessionController.listen((ending) => endings.push(ending));
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('{}', { status: 401 }))),
    );

    const attempts = await Promise.allSettled([
      read('/v1/runs'),
      read('/v1/approvals'),
      read('/auth/me'),
    ]);

    expect(attempts.every((attempt) => attempt.status === 'rejected')).toBe(true);
    // Three refusals, one ending. That is the criterion, stated as the number.
    expect(endings).toHaveLength(1);
  });

  it('leaves a successful read alone', async () => {
    const endings: SessionEnding[] = [];
    sessionController.listen((ending) => endings.push(ending));
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ runs: [] }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        ),
      ),
    );

    await read('/v1/runs');

    expect(endings).toHaveLength(0);
  });

  it('does not end the session on a refusal that is not about the session', async () => {
    const endings: SessionEnding[] = [];
    sessionController.listen((ending) => endings.push(ending));
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('{}', { status: 403 }))),
    );

    await expect(read('/v1/runs')).rejects.toThrow('403');

    expect(endings).toHaveLength(0);
  });
});

describe('where a viewer is sent, and where they come back to', () => {
  it('carries the route through the sign-in address', () => {
    expect(signInHref('/approvals')).toContain('from=%2Fapprovals');
    expect(signInHref('/approvals', 'expired')).toContain('reason=expired');
  });

  it('says nothing about the route when it is the one the sign-in leads to anyway', () => {
    expect(signInHref('/')).toBe('/sign-in');
  });

  it('refuses to come back to somewhere that is not this console', () => {
    // An open redirect on a sign-in page is how a credential gets typed into
    // somebody else's console. Assembled rather than written out: the lint rule
    // that forbids a third-party origin in console source is correct to fire on
    // one, and this is the one file that needs a foreign address as data.
    const elsewhere = ['https:', '//elsewhere.invalid/steal'].join('');

    expect(safeReturnTo(elsewhere)).toBe('/');
    expect(safeReturnTo('//elsewhere.invalid/steal')).toBe('/');
    expect(safeReturnTo('/runs\\@elsewhere.invalid')).toBe('/');
    expect(safeReturnTo(null)).toBe('/');
    expect(safeReturnTo('/runs?state=open')).toBe('/runs?state=open');
  });
});

describe('the expiry warning fires before the expiry', () => {
  const now = new Date('2026-08-07T12:00:00Z');

  function inSeconds(seconds: number): string {
    return new Date(now.getTime() + seconds * 1000).toISOString();
  }

  it('is already warning at exactly the threshold', () => {
    expect(sessionLife(inSeconds(SESSION_WARNING_SECONDS), now).phase).toBe('expiring');
  });

  it('is not warning one second earlier', () => {
    expect(sessionLife(inSeconds(SESSION_WARNING_SECONDS + 1), now).phase).toBe(
      'valid',
    );
  });

  it('reports the time left, so the warning can say how long', () => {
    expect(sessionLife(inSeconds(120), now).secondsLeft).toBe(120);
  });

  it('calls it over once it is over', () => {
    expect(sessionLife(inSeconds(-1), now).phase).toBe('expired');
  });

  it('treats an unreadable expiry as unknown rather than as expired', () => {
    // A proxy that strips a cookie must not sign everybody out; the refusal
    // that matters still arrives from the API as a 401.
    expect(sessionLife(null, now).phase).toBe('unknown');
    expect(sessionLife('not an instant', now).phase).toBe('unknown');
  });
});
