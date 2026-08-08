import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { AREAS } from '@/shell/routes';
import { SESSION_COOKIE, SIGN_IN_PATH } from '@/session/cookies';
import { guard } from '@/session/guard';

/**
 * Every route, opened unauthenticated, and what it may say.
 *
 * The enumeration is the point. This walks the route manifest rather than a
 * list written out here, so an area added tomorrow is covered by this test
 * having already been written — which is the property the plan names as the one
 * a file-based router loses first.
 */

const NONE: ReadonlyMap<string, string> = new Map();
const SIGNED_IN: ReadonlyMap<string, string> = new Map([[SESSION_COOKIE, 'opaque']]);

describe('an unauthenticated visitor', () => {
  it.each(AREAS.map((area) => [area.id, area.path] as const))(
    'is sent to the sign-in from %s',
    (_id, path) => {
      const decision = guard(path, '', NONE);

      expect(decision.kind).toBe('redirect');
      if (decision.kind === 'redirect') {
        expect(decision.to.startsWith(SIGN_IN_PATH)).toBe(true);
      }
    },
  );

  it('is sent to the sign-in from a route that does not exist either', () => {
    // Otherwise the not-found page is a way to learn that the deployment is
    // there, which is one bit more than an unauthenticated visitor gets.
    expect(guard('/no-such-area', '', NONE).kind).toBe('redirect');
  });

  it('keeps the route they were trying to reach', () => {
    const decision = guard('/approvals', '?state=pending', NONE);

    expect(decision.kind).toBe('redirect');
    if (decision.kind === 'redirect') {
      expect(decision.to).toContain('from=%2Fapprovals%3Fstate%3Dpending');
    }
  });

  it('reaches the sign-in itself, and the route handler it posts to', () => {
    expect(guard(SIGN_IN_PATH, '', NONE).kind).toBe('allow');
    expect(guard('/api/session', '', NONE).kind).toBe('allow');
  });

  it('is not let through by an empty cookie', () => {
    expect(guard('/', '', new Map([[SESSION_COOKIE, '']])).kind).toBe('redirect');
  });
});

describe('a signed-in operator', () => {
  it.each(AREAS.map((area) => [area.id, area.path] as const))(
    'reaches %s directly',
    (_id, path) => {
      expect(guard(path, '', SIGNED_IN).kind).toBe('allow');
    },
  );
});

describe('the guard sits above the router rather than inside a page', () => {
  const source = readFileSync(join(process.cwd(), 'middleware.ts'), 'utf8');

  it('is the middleware, which Next runs before routing', () => {
    expect(source).toContain('export function middleware');
    expect(source).toContain("from '@/session/guard'");
  });

  it('covers every path but the build output, as an exclusion rather than a list', () => {
    // A list of guarded pages is a list somebody forgets to extend, and the one
    // they forget is the page nobody is watching.
    expect(source).toContain('matcher');
    expect(source).toContain('_next/static');
    expect(source).toMatch(/matcher:\s*\['\/\(\(\?!/);
  });

  it('is the only place the session cookie decides anything', () => {
    // Grepped rather than reasoned about: a second check somewhere in `app/`
    // would be a second rule, and the second rule is the one that is wrong.
    const pages = readFileSync(join(process.cwd(), 'src/session/guard.ts'), 'utf8');
    expect(pages).toContain('SESSION_COOKIE');
  });
});
