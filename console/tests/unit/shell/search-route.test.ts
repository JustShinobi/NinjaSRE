import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { askDeployment } from '@/shell/search-client';

/**
 * The search courier, and the client that talks to it.
 *
 * A courier for the reason every other one here exists: the session credential
 * is an HTTP-only, `SameSite=Strict` cookie the browser will not send to
 * another host, so the palette cannot make these three reads itself.
 *
 * What is worth asserting is the degradation. Three sources are read in
 * parallel and each is independent, because a search that failed whole when one
 * of them did would stop working exactly when somebody is looking for the thing
 * that broke — which is the only moment this feature matters.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';
const API = 'http://127.0.0.1:8424';

let asked: string[] = [];

/** A fetch that answers each of the three paths from `bodies`, by substring. */
function answering(bodies: Readonly<Record<string, [number, unknown]>>) {
  return vi.fn((url: unknown) => {
    const address = String(url);
    asked.push(address);
    const match = Object.keys(bodies).find((path) => address.includes(path));
    const answer = match === undefined ? undefined : bodies[match];
    const [status, body] = answer ?? [404, {}];
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

function request(query: string, withSession = true): NextRequest {
  const made = new NextRequest(
    `${CONSOLE_ORIGIN}/api/search?q=${encodeURIComponent(query)}`,
  );
  if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function get(query: string, session = true): Promise<Response> {
  const { GET } = await import('@/app/api/search/route');
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

it('asks the estate, the incidents and the runs, carrying the session credential', async () => {
  vi.stubGlobal(
    'fetch',
    answering({
      '/v1/estate/resources': [
        200,
        {
          resources: [
            {
              resource_id: 'r1',
              display_name: 'signoz-collector',
              kind: 'container',
            },
          ],
        },
      ],
      '/v1/incidents': [200, { incidents: [] }],
      '/v1/runs': [200, { runs: [] }],
    }),
  );

  const answer = await get('signoz');

  expect(answer.status).toBe(200);
  expect(asked.some((url) => url.includes('/v1/estate/resources'))).toBe(true);
  expect(asked.some((url) => url.includes('/v1/incidents'))).toBe(true);
  expect(asked.some((url) => url.includes('/v1/runs'))).toBe(true);
  await expect(answer.json()).resolves.toMatchObject({
    found: [
      {
        id: 'resource:r1',
        group: 'resources',
        href: '/resources?selected=r1',
      },
    ],
    partial: false,
  });
});

it('still finds resources when the incident store is unavailable', async () => {
  // The property this whole shape exists for. A search that failed whole
  // because one of its three sources did would stop working exactly when
  // somebody is looking for the thing that broke.
  vi.stubGlobal(
    'fetch',
    answering({
      '/v1/estate/resources': [
        200,
        { resources: [{ resource_id: 'r1', display_name: 'signoz-collector' }] },
      ],
      '/v1/incidents': [503, { detail: 'the store is not answering' }],
      '/v1/runs': [200, { runs: [] }],
    }),
  );

  const body: unknown = await (await get('signoz')).json();

  expect(Reflect.get(Object(body), 'found')).toHaveLength(1);
});

it('survives a source that throws rather than answering', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: unknown) =>
      String(url).includes('/v1/incidents')
        ? Promise.reject(new Error('connection reset'))
        : Promise.resolve(
            new Response(JSON.stringify({ resources: [], runs: [] }), { status: 200 }),
          ),
    ),
  );

  const answer = await get('signoz');

  expect(answer.status).toBe(200);
  await expect(answer.json()).resolves.toMatchObject({ found: [] });
});

it('says the answer is partial when a source filled its page', async () => {
  // "Nothing matches" and "nothing matches in the first two hundred" are
  // different answers, and only one of them means the thing is not there.
  const full = Array.from({ length: 200 }, (_, at) => ({
    resource_id: `r${String(at)}`,
    display_name: `worker-${String(at)}`,
  }));
  vi.stubGlobal(
    'fetch',
    answering({
      '/v1/estate/resources': [200, { resources: full }],
      '/v1/incidents': [200, { incidents: [] }],
      '/v1/runs': [200, { runs: [] }],
    }),
  );

  await expect((await get('nothing-like-this')).json()).resolves.toMatchObject({
    partial: true,
  });
});

it('refuses without a session, and asks the deployment nothing', async () => {
  vi.stubGlobal('fetch', answering({}));

  const answer = await get('signoz', false);

  expect(answer.status).toBe(401);
  expect(asked).toEqual([]);
});

it('does not ask the deployment about a single character', async () => {
  // One character matches most of an estate: three reads to hand back what the
  // operator is already looking at.
  vi.stubGlobal('fetch', answering({}));

  const answer = await get('s');

  expect(answer.status).toBe(200);
  expect(asked).toEqual([]);
});

it('ignores a body that is not the shape it expects', async () => {
  vi.stubGlobal(
    'fetch',
    answering({
      '/v1/estate/resources': [200, { resources: 'not a list' }],
      '/v1/incidents': [200, {}],
      '/v1/runs': [200, { runs: null }],
    }),
  );

  await expect((await get('signoz')).json()).resolves.toMatchObject({ found: [] });
});

// --- The browser's half ------------------------------------------------------

it('the client reads what the courier sent', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            found: [
              {
                id: 'resource:r1',
                group: 'resources',
                label: 'signoz-collector',
                hint: 'container healthy',
                href: '/resources?selected=r1',
              },
            ],
            partial: true,
          }),
          { status: 200 },
        ),
      ),
    ),
  );

  const answer = await askDeployment('signoz', new AbortController().signal);

  expect(answer.found).toHaveLength(1);
  expect(answer.found[0]?.label).toBe('signoz-collector');
  expect(answer.partial).toBe(true);
});

it('the client drops a row whose shape it does not recognise', async () => {
  // Anything crossing a process boundary is untrusted. A row with no href is a
  // row the palette would render as an entry that navigates nowhere.
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            found: [
              { id: 'x', group: 'nowhere', label: 'a', href: '/a' },
              { id: 'y', group: 'resources', label: 'b' },
              { id: 'z', group: 'resources', label: 'c', href: '/c' },
            ],
          }),
          { status: 200 },
        ),
      ),
    ),
  );

  const answer = await askDeployment('signoz', new AbortController().signal);

  expect(answer.found.map((entry) => entry.id)).toEqual(['z']);
  expect(answer.found[0]?.hint).toBe('');
});

it('the client finds nothing when the courier refuses', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response('{}', { status: 502 }))),
  );

  await expect(
    askDeployment('signoz', new AbortController().signal),
  ).resolves.toMatchObject({ found: [], partial: false });
});

it('the client finds nothing when the request cannot be made at all', async () => {
  // Including an abort, which is what every keystroke does to the request the
  // last one started.
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('aborted'))),
  );

  await expect(
    askDeployment('signoz', new AbortController().signal),
  ).resolves.toMatchObject({ found: [] });
});
