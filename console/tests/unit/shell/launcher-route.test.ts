import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { askLauncher, EMPTY_BRIEFING, LAUNCHER_ENDPOINT } from '@/shell/launcher';

import { bodyFor } from '../../../scripts/fixture-server.mjs';

/**
 * The launcher courier, and the client that asks it.
 *
 * The briefing the investigate drawer opens with — the viewer's team, the
 * subject that keeps firing, the unhealthy count — costs three gateway reads,
 * and the drawer is a thing most page views never open. So the frame no longer
 * pays for it on every render: the drawer asks this courier when it opens, and
 * the courier does what the layout used to do, for that one viewer.
 *
 * The team is the viewer's own, resolved from the session here, never taken
 * from the request. A courier that let the browser name a team would be a
 * courier that answers with somebody else's briefing.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';
const API = 'http://127.0.0.1:8424';

let asked: string[] = [];

/** A fetch that answers from the committed dataset, and remembers what it was asked. */
function servingDataset() {
  return vi.fn((url: unknown) => {
    const path = new URL(String(url)).pathname;
    asked.push(path);
    const body: unknown = bodyFor('populated', path);
    if (body === null || body === undefined) {
      return Promise.resolve(new Response('{}', { status: 404 }));
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

function request(query = '', withSession = true): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}${LAUNCHER_ENDPOINT}${query}`);
  if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function get(query = '', session = true): Promise<Response> {
  const { GET } = await import('@/app/api/launcher/route');
  return GET(request(query, session));
}

beforeEach(() => {
  asked = [];
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', API);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it('refuses without a session, and asks the deployment nothing', async () => {
  vi.stubGlobal('fetch', servingDataset());

  const answer = await get('', false);

  expect(answer.status).toBe(401);
  expect(asked).toEqual([]);
});

it('answers the briefing for the viewer the session resolves to', async () => {
  vi.stubGlobal('fetch', servingDataset());

  const answer = await get();

  expect(answer.status).toBe(200);
  const body: unknown = await answer.json();
  // The dataset's principal sits at `org-northwind`, which the tree names
  // "Northwind"; its estate summary counts fourteen unhealthy resources.
  expect(body).toMatchObject({ teamName: 'Northwind', unhealthy: 14 });
  const recurring: unknown = Reflect.get(Object(body), 'recurring');
  expect(
    recurring === null ||
      (typeof Reflect.get(Object(recurring), 'subject') === 'string' &&
        typeof Reflect.get(Object(recurring), 'count') === 'number'),
  ).toBe(true);
  expect(asked).toContain('/auth/me');
  expect(asked).toContain('/v1/incidents');
  expect(asked).toContain('/v1/estate/summary');
  expect(asked).toContain('/v1/config');
});

it('names the team the session resolves to, whatever the request says', async () => {
  // The browser does not get to pick whose briefing it reads.
  vi.stubGlobal('fetch', servingDataset());

  const body: unknown = await (await get('?team=team-storage')).json();

  expect(body).toMatchObject({ teamName: 'Northwind' });
});

it('refuses when the deployment no longer accepts the session', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response('{}', { status: 401 }))),
  );

  const answer = await get();

  expect(answer.status).toBe(401);
});

it('degrades to the empty briefing when the three reads fail', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: unknown) => {
      const path = new URL(String(url)).pathname;
      if (path === '/auth/me') {
        return Promise.resolve(
          new Response(JSON.stringify(bodyFor('populated', path)), { status: 200 }),
        );
      }
      return Promise.reject(new TypeError('fetch failed'));
    }),
  );

  const answer = await get();

  expect(answer.status).toBe(200);
  await expect(answer.json()).resolves.toEqual(EMPTY_BRIEFING);
});

// --- The browser's half ------------------------------------------------------

it('the client asks the courier once, uncached, and reads what it sent', async () => {
  const fetching = vi.fn(() =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          teamName: 'Platform',
          recurring: { subject: 'RedisExporterDown', count: 8 },
          unhealthy: 14,
        }),
        { status: 200 },
      ),
    ),
  );
  vi.stubGlobal('fetch', fetching);

  const briefing = await askLauncher(new AbortController().signal);

  expect(briefing).toEqual({
    teamName: 'Platform',
    recurring: { subject: 'RedisExporterDown', count: 8 },
    unhealthy: 14,
  });
  expect(fetching).toHaveBeenCalledTimes(1);
  const [address, init] = fetching.mock.calls[0] as unknown as [string, RequestInit];
  expect(address).toBe(LAUNCHER_ENDPOINT);
  expect(init.cache).toBe('no-store');
});

it('the client keeps the empty briefing when the courier refuses', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response('{}', { status: 401 }))),
  );

  await expect(askLauncher(new AbortController().signal)).resolves.toEqual(
    EMPTY_BRIEFING,
  );
});

it('the client keeps the empty briefing when the request cannot be made', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('aborted'))),
  );

  await expect(askLauncher(new AbortController().signal)).resolves.toEqual(
    EMPTY_BRIEFING,
  );
});

it('the client drops a body whose shape it does not recognise', async () => {
  // Anything crossing a process boundary is untrusted. A recurring subject
  // with no count would render as "keeps firing (undefined times)".
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            teamName: 42,
            recurring: { subject: 'RedisExporterDown' },
            unhealthy: 'many',
          }),
          { status: 200 },
        ),
      ),
    ),
  );

  await expect(askLauncher(new AbortController().signal)).resolves.toEqual(
    EMPTY_BRIEFING,
  );
});
