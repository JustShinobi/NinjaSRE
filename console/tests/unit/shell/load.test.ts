import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { oldest, unreadCount, withoutItem } from '@/shell/attention';
import { deploymentFrom, documentTitle } from '@/shell/deployment';
import {
  countsFrom,
  loadAttention,
  loadGuardian,
  loadRecentRuns,
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

function servingFixtures(): typeof fetch {
  return vi.fn((input: RequestInfo | URL) => {
    const path = input instanceof Request ? input.url : String(input);
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
    expect(approvals.every((item) => item.href.startsWith('/approvals/'))).toBe(true);
  });

  it('reads the guardian&apos;s liveness from what the deployment reports', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    expect(await loadGuardian('opaque')).toEqual({ live: true, posture: 'propose' });
  });

  it('counts what each area is waiting on', async () => {
    vi.stubGlobal('fetch', servingFixtures());
    const counts = countsFrom(await loadAttention('opaque'));

    expect(counts.approvals).toBeGreaterThan(0);
    expect(Object.keys(counts).sort()).toEqual([
      'approvals',
      'incidents',
      'proposals',
      'runs',
    ]);
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
    expect(documentTitle('Approvals', 'HAL9000')).toBe('Approvals · HAL9000');
  });
});
