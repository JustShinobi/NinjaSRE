import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { oldest, unreadCount, withoutItem } from '@/shell/attention';
import { deploymentFrom, documentTitle } from '@/shell/deployment';
import {
  countsFrom,
  loadAttention,
  loadGuardian,
  loadLauncher,
  loadRecentRuns,
  loadSetup,
  loadStopped,
  loadViewer,
  stoppageFrom,
} from '@/shell/load';

/**
 * What the shell reads before it draws itself, against the committed dataset.
 *
 * The fixture set is the same anonymised capture the design was drawn from, so
 * these assertions are about the console rather than about whatever a live
 * deployment happened to be doing.
 *
 * Everything except the viewer degrades rather than throws. A notification count
 * that could not be read is a missing count; it must not be a console nobody can
 * sign in to.
 */

/** The body the committed dataset answers `slug` with, for the populated scenario. */
function fixture(slug: string): unknown {
  const path = join(
    process.cwd(),
    '..',
    'fixtures',
    'scenarios',
    'populated',
    `${slug}.json`,
  );
  const loaded: unknown = JSON.parse(readFileSync(path, 'utf8'));
  const responses: unknown = Reflect.get(Object(loaded), 'responses');
  if (!Array.isArray(responses)) throw new Error(`${slug}.json holds no responses`);
  return Reflect.get(Object(responses[0]), 'body');
}

const BY_PATH: Readonly<Record<string, string>> = {
  '/auth/me': 'principal',
  '/v1/runs': 'runs',
  '/v1/approvals': 'approvals',
  '/health/ready': 'health',
};

/** The address a stub was asked for, as a string, whatever shape it arrived in. */
function addressOf(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

/** The path alone — a query string is the read's business, not the dataset's. */
function pathOf(input: RequestInfo | URL): string {
  return addressOf(input).split('?')[0] ?? '';
}

function servingFixtures(): typeof fetch {
  return vi.fn((input: RequestInfo | URL) => {
    const path = pathOf(input);
    const slug = Object.entries(BY_PATH).find(([known]) => path.endsWith(known))?.[1];
    if (slug === undefined) {
      return Promise.resolve(new Response('{}', { status: 404 }));
    }
    return Promise.resolve(
      new Response(JSON.stringify(fixture(slug)), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('resolving what the shell needs', () => {
  it('resolves the viewer once, with the permissions the server gave', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    const viewer = await loadViewer('opaque');

    expect(viewer.principalId).toBe('user-operator');
    expect(viewer.permissions).toContain('audit.read');
  });

  it('presents the credential as a bearer token and caches nothing', async () => {
    const fetching = servingFixtures();
    vi.stubGlobal('fetch', fetching);
    await loadViewer('opaque');

    const [, init] = (fetching as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get('authorization')).toBe('Bearer opaque');
    // The shell is per viewer and per instant; a cached copy of it is somebody
    // else's permissions rendered for this person.
    expect(init.cache).toBe('no-store');
  });

  it('refuses rather than inventing a viewer when the API will not say', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('{}', { status: 401 }))),
    );
    await expect(loadViewer('stale')).rejects.toThrow();
  });

  it('offers the recent runs the dataset holds', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    const runs = await loadRecentRuns('opaque');

    expect(runs.length).toBeGreaterThan(0);
    expect(runs[0]?.id).toMatch(/^run-/);
  });

  it('lists what is waiting on a person, from more than one source', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    const waiting = await loadAttention('opaque');

    expect(waiting.length).toBeGreaterThan(0);
    expect(waiting.every((item) => item.id !== '')).toBe(true);
    expect(new Set(waiting.map((item) => item.kind)).has('approval')).toBe(true);
  });

  it('lists no approval that has already been decided', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    const waiting = await loadAttention('opaque');
    const approvals = waiting.filter((item) => item.kind === 'approval');

    expect(approvals.length).toBeGreaterThan(0);
    // Every one of them was pending in the dataset; a decided one appearing
    // here is the notification centre people learn to distrust.
    expect(
      approvals.every((item) => item.href.startsWith('/decisions?tab=actions')),
    ).toBe(true);
  });

  it('reads the guardian&apos;s liveness from what the deployment reports', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    expect(await loadGuardian('opaque')).toEqual({ live: true, posture: 'propose' });
  });

  it('counts only a pending, unexpired approval toward the decisions badge', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input instanceof Request ? input.url : String(input);
        if (path.endsWith('/v1/approvals')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                approvals: [
                  {
                    approval_id: 'apr-pending',
                    state: 'pending',
                    summary: 'x',
                    action: 'y',
                  },
                  {
                    approval_id: 'apr-expired',
                    state: 'expired',
                    summary: 'x',
                    action: 'y',
                  },
                ],
              }),
              { status: 200, headers: { 'content-type': 'application/json' } },
            ),
          );
        }
        return Promise.resolve(new Response('{}', { status: 404 }));
      }),
    );

    const counts = countsFrom(await loadAttention('opaque'));

    expect(counts.decisions).toBe(1);
  });

  it('counts nothing toward the decisions badge when only an expired approval remains', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input instanceof Request ? input.url : String(input);
        if (path.endsWith('/v1/approvals')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                approvals: [
                  {
                    approval_id: 'apr-expired',
                    state: 'expired',
                    summary: 'x',
                    action: 'y',
                  },
                ],
              }),
              { status: 200, headers: { 'content-type': 'application/json' } },
            ),
          );
        }
        return Promise.resolve(new Response('{}', { status: 404 }));
      }),
    );

    const counts = countsFrom(await loadAttention('opaque'));

    expect(counts.decisions).toBe(0);
  });

  it('counts what each area is waiting on', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    const counts = countsFrom(await loadAttention('opaque'));

    // Decisions is one area for both kinds now: an approval waiting and a
    // proposal waiting both count toward the same badge.
    expect(counts.decisions).toBeGreaterThan(0);
    expect(Object.keys(counts).sort()).toEqual(['decisions', 'incidents', 'runs']);
  });
});

describe('the three attention reads', () => {
  /**
   * One item from each source, so the order the items come back in says which
   * source each one was read from.
   */
  const BODIES: Readonly<Record<string, unknown>> = {
    '/v1/approvals': {
      approvals: [
        {
          approval_id: 'apr-1',
          state: 'pending',
          summary: 'restart the collector',
          action: 'restart',
          requested_at: '2026-08-07T09:00:00Z',
        },
      ],
    },
    '/v1/proposals': {
      proposals: [
        {
          proposal_id: 'prp-1',
          summary: 'raise the threshold',
          proposal_type: 'detector',
          proposed_at: '2026-08-07T09:10:00Z',
        },
      ],
    },
    '/v1/runs': {
      runs: [
        {
          run_id: 'run-1',
          status: 'failed',
          summary: 'disk pressure',
          started_at: '2026-08-07T09:20:00Z',
        },
      ],
    },
  };

  function known(input: RequestInfo | URL): string | undefined {
    const path = pathOf(input);
    return Object.keys(BODIES).find((known) => path.endsWith(known));
  }

  function json(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    });
  }

  it('are all in flight before any of them has answered', async () => {
    // Nobody answers until every read has been issued. Three reads made one
    // after the other never get past the first; three made together are all
    // on the wire by the time the first macrotask runs.
    const started: string[] = [];
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = known(input);
        started.push(path ?? 'unknown');
        await gate;
        return path === undefined ? json({}, 404) : json(BODIES[path]);
      }),
    );

    const pending = loadAttention('opaque');
    try {
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(started).toEqual(['/v1/approvals', '/v1/proposals', '/v1/runs']);
    } finally {
      release?.();
    }

    // Issued together, still processed in the order the sources are listed —
    // approvals first, failures last — whichever one answered first.
    expect((await pending).map((item) => item.kind)).toEqual([
      'approval',
      'proposal',
      'failure',
    ]);
  });

  it('keep the other two when one of them is refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = known(input);
        if (path === '/v1/proposals') return Promise.resolve(json({}, 500));
        return Promise.resolve(path === undefined ? json({}, 404) : json(BODIES[path]));
      }),
    );

    expect((await loadAttention('opaque')).map((item) => item.kind)).toEqual([
      'approval',
      'failure',
    ]);
  });

  it('keep the other two when one of them cannot reach the deployment', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = known(input);
        if (path === '/v1/approvals') return Promise.reject(new TypeError('network'));
        return Promise.resolve(path === undefined ? json({}, 404) : json(BODIES[path]));
      }),
    );

    expect((await loadAttention('opaque')).map((item) => item.kind)).toEqual([
      'proposal',
      'failure',
    ]);
  });

  it('still surface a failure that is neither a refusal nor the network', async () => {
    // A refusal and an unreachable deployment are the two ways a read is
    // allowed to come back empty. Anything else is a defect, and swallowing
    // it would be a notification centre that is silently, permanently empty.
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = known(input);
        if (path === '/v1/runs') return Promise.reject(new Error('unexpected'));
        return Promise.resolve(path === undefined ? json({}, 404) : json(BODIES[path]));
      }),
    );

    await expect(loadAttention('opaque')).rejects.toThrow('unexpected');
  });
});

describe('what the two runs reads ask the gateway for', () => {
  /**
   * The runs list is the largest payload of every render, and the frame used
   * to read the whole first page of it twice for two small needs. Each read
   * now asks for exactly what it is for: the palette for a page of recent
   * runs, the attention list for the runs that ended badly. Two small reads
   * at two addresses, on purpose — a shared address would be deduplicated
   * into one large read again.
   */
  function recording(): { fetching: typeof fetch; addresses: string[] } {
    const addresses: string[] = [];
    const fetching = vi.fn((input: RequestInfo | URL) => {
      addresses.push(addressOf(input));
      return Promise.resolve(
        new Response(JSON.stringify({ runs: [], approvals: [], proposals: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });
    return { fetching, addresses };
  }

  it('asks for a page of twenty recent runs for the palette', async () => {
    const { fetching, addresses } = recording();
    vi.stubGlobal('fetch', fetching);

    await loadRecentRuns('opaque');

    expect(addresses).toEqual(['/v1/runs?limit=20']);
  });

  it('asks only for the runs that ended badly for the attention list', async () => {
    const { fetching, addresses } = recording();
    vi.stubGlobal('fetch', fetching);

    await loadAttention('opaque');

    expect(addresses.filter((address) => address.includes('/v1/runs'))).toEqual([
      '/v1/runs?status=failed&status=cancelled&status=interrupted&limit=20',
    ]);
  });

  it('reports an interrupted run as needing a person, and knows no "error" status', async () => {
    // `interrupted` means nobody knows how far the run got, which is exactly
    // a run that needs a person. `error` is not a status this gateway has; a
    // row claiming it is not one of the terminal words and is not counted.
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (!pathOf(input).endsWith('/v1/runs')) {
          return Promise.resolve(new Response('{}', { status: 404 }));
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              runs: [
                { run_id: 'run-interrupted', status: 'interrupted', summary: 's' },
                { run_id: 'run-error', status: 'error', summary: 's' },
                { run_id: 'run-failed', status: 'failed', summary: 's' },
                { run_id: 'run-cancelled', status: 'cancelled', summary: 's' },
              ],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        );
      }),
    );

    const failures = (await loadAttention('opaque')).filter(
      (item) => item.kind === 'failure',
    );

    expect(failures.map((item) => item.id)).toEqual([
      'run-interrupted',
      'run-failed',
      'run-cancelled',
    ]);
  });
});

describe('what the frame knows about setup', () => {
  it('reads runtimeComposed true from the checklist a finished deployment reports', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    // 'populated' is a fully finished deployment; its own fifth checklist step
    // has to say a runtime exists, or every other screen that reads "this
    // deployment is fully set up" from the same fixture would be reading a
    // document that contradicts itself — the exact inconsistency fixed in
    // tools/mockplane/dataset/served.py earlier in this spec.
    expect((await loadSetup('opaque')).runtimeComposed).toBe(true);
  });

  it('reads runtimeComposed false when the checklist says the runtime step is not done', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              complete: false,
              provider: 'verified',
              integrations: [],
              steps: [
                {
                  name: 'investigation-runtime',
                  title: 'Give it something to investigate with',
                  state: 'ready',
                  detail: 'nothing here can drive an investigation yet',
                  action:
                    'whoever operates this deployment supplies the investigation runtime',
                  readiness: 'absent',
                },
              ],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        ),
      ),
    );

    expect((await loadSetup('opaque')).runtimeComposed).toBe(false);
  });

  it('assumes composed when the checklist declares no such step at all', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              complete: true,
              provider: 'verified',
              integrations: [],
              steps: [],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        ),
      ),
    );

    // Absent from what the deployment reports — an older backend, before this
    // step existed — reads the same as composed: this fact exists to state a
    // dependency the deployment can prove is missing, not to invent one it
    // has never declared.
    expect((await loadSetup('opaque')).runtimeComposed).toBe(true);
  });

  it('assumes composed when the read fails, so a working deployment carries no false caveat', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('network'))),
    );

    expect(await loadSetup('opaque')).toEqual({
      checklistComplete: false,
      integrationsConfigured: true,
      runtimeComposed: true,
    });
  });
});

describe('whether every automated write is stopped', () => {
  it('reports who stopped it and since when, from the organisation scope', () => {
    expect(
      stoppageFrom({
        engaged: true,
        scopes: {
          '*': {
            scope: '*',
            engaged_by: 'avery',
            engaged_at: '2026-08-07T09:00:00Z',
            reason: '',
          },
        },
      }),
    ).toEqual({ engaged: true, by: 'avery', since: '2026-08-07T09:00:00Z' });
  });

  it('prefers the organisation scope over a narrower one', () => {
    expect(
      stoppageFrom({
        engaged: true,
        scopes: {
          'team-platform': { engaged_by: 'reese', engaged_at: '2026-08-07T09:00:00Z' },
          '*': { engaged_by: 'avery', engaged_at: '2026-08-07T10:00:00Z' },
        },
      }),
    ).toEqual({ engaged: true, by: 'avery', since: '2026-08-07T10:00:00Z' });
  });

  it('says nothing is stopped rather than guessing, when the deployment does not say', () => {
    expect(stoppageFrom({ engaged: false })).toEqual({
      engaged: false,
      by: null,
      since: null,
    });
    expect(stoppageFrom({})).toEqual({ engaged: false, by: null, since: null });
  });

  it('reports engaged with no who or since when the deployment could not say either', () => {
    expect(stoppageFrom({ engaged: true, scopes: {} })).toEqual({
      engaged: true,
      by: null,
      since: null,
    });
  });

  it('degrades to not stopped rather than claiming a stop nobody engaged', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('network'))),
    );
    expect(await loadStopped('opaque')).toEqual({
      engaged: false,
      by: null,
      since: null,
    });
  });
});

describe('a deployment that cannot be reached', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('network'))),
    );
  });

  it('leaves the palette without recent runs rather than without a console', async () => {
    expect(await loadRecentRuns('opaque')).toEqual([]);
  });

  it('leaves the notification centre empty rather than broken', async () => {
    expect(await loadAttention('opaque')).toEqual([]);
  });

  it('reports the guardian as silent rather than as acting', async () => {
    // The one direction this must never be wrong in: a deployment that has not
    // said anything is not a deployment that is allowed to act.
    expect(await loadGuardian('opaque')).toEqual({ live: false, posture: 'propose' });
  });

  it('offers the investigate drawer only the audit, rather than an invented suggestion', async () => {
    // Read by the launcher courier now rather than by the frame, and the
    // degradation is the same either way: no team name, no recurring subject,
    // nothing unhealthy — the honest floor, never a fabricated incident.
    expect(await loadLauncher('opaque', 'org-northwind')).toEqual({
      teamName: '',
      recurring: null,
      unhealthy: 0,
    });
  });
});

describe('a deployment that refuses these reads', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('{}', { status: 403 }))),
    );
  });

  it('degrades each panel rather than the shell', async () => {
    expect(await loadRecentRuns('opaque')).toEqual([]);
    expect(await loadAttention('opaque')).toEqual([]);
    expect((await loadGuardian('opaque')).live).toBe(false);
  });
});

describe('the attention list itself', () => {
  const items = [
    {
      id: 'a',
      kind: 'approval' as const,
      title: 'a',
      detail: '',
      href: '/a',
      since: '2026-08-07T09:00:00Z',
    },
    {
      id: 'b',
      kind: 'failure' as const,
      title: 'b',
      detail: '',
      href: '/b',
      since: '2026-08-07T11:00:00Z',
    },
  ];

  it('drops one without touching the rest', () => {
    expect(withoutItem(items, 'a').map((item) => item.id)).toEqual(['b']);
    expect(unreadCount(items)).toBe(2);
  });

  it('names the one that has been waiting longest', () => {
    expect(oldest(items)?.id).toBe('a');
  });

  it('answers nothing for an empty list, and ignores an unreadable instant', () => {
    expect(oldest([])).toBeUndefined();
    const [first] = items;
    expect(first).toBeDefined();
    if (first === undefined) return;
    expect(oldest([{ ...first, since: 'not an instant' }])).toBeUndefined();
  });
});

describe('what the deployment is called', () => {
  it('takes its name and zone from the environment', () => {
    expect(
      deploymentFrom({
        NINJASRE_CONSOLE_DEPLOYMENT: 'HAL9000',
        NINJASRE_CONSOLE_TIMEZONE: 'Europe/Lisbon',
      }),
    ).toEqual({ name: 'HAL9000', timezone: 'Europe/Lisbon' });
  });

  it('has an answer when the environment says nothing', () => {
    expect(deploymentFrom({})).toEqual({ name: 'NinjaSRE', timezone: 'UTC' });
    expect(deploymentFrom({ NINJASRE_CONSOLE_DEPLOYMENT: '  ' }).name).toBe('NinjaSRE');
  });

  it('puts the page in front of the deployment in a title', () => {
    // A browser truncates a tab from the right, and the page is the part that
    // distinguishes one tab from the next.
    expect(documentTitle('Actions awaiting approval', 'HAL9000')).toBe(
      'Actions awaiting approval · HAL9000',
    );
  });
});
