import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { vi } from 'vitest';

// The committed dataset, resolved by the same table the visual capture serves
// it with. Importing it rather than restating it is what makes a screen tested
// in `jsdom` and a screen photographed in a browser two views of one dataset.
import { bodyFor } from '../../../scripts/fixture-server.mjs';

import type { SurfaceContext } from '@/surfaces/context';
import type { Viewer } from '@/session/viewer';

/**
 * Every screen, against the committed dataset.
 *
 * The alternative — a hand-written payload per test — is how a console's tests
 * come to assert against a shape the deployment stopped sending a year ago. The
 * dataset here is the same anonymised capture the design was drawn from, so a
 * screen that renders in this suite is a screen that renders against the data
 * the mockups show, and a difference is a difference in the console.
 */

/** The scenarios the dataset carries. */
export const SCENARIOS = ['empty', 'first-run', 'populated', 'restricted'] as const;

export type Scenario = (typeof SCENARIOS)[number];

/** A base for parsing a path-only address. Never contacted, and built rather than written. */
const BASE = ['http:', '//fixtures.invalid'].join('');

/**
 * Answer every request from `scenario` for the rest of the test.
 *
 * A path the dataset does not carry answers 404, which is what an unpopulated
 * deployment does with a projected endpoint — and is the case the empty states
 * exist for.
 */
export function serveScenario(scenario: Scenario, principal?: unknown): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const body: unknown =
      path === '/auth/me' && principal !== undefined
        ? principal
        : bodyFor(scenario, path);
    if (body === null || body === undefined) {
      return Promise.resolve(
        new Response('{}', {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

/**
 * Refuse every read a *panel* makes, while the session still resolves.
 *
 * The principal is answered because a refused viewer is a refused session rather
 * than a failed panel, and the two are different screens: one is the sign-in
 * page. What this produces is the case the panel boundary exists for — a viewer
 * who is signed in, looking at a page whose data nobody would give it.
 */
export function serveRefusal(status = 503): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/auth/me') {
      return Promise.resolve(
        new Response(JSON.stringify(bodyFor('populated', path)), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }
    return Promise.resolve(
      new Response('{}', { status, headers: { 'content-type': 'application/json' } }),
    );
  });
}

/** The principal the dataset records, as the console resolves it. */
export function datasetViewer(scenario: Scenario = 'populated'): Viewer {
  const path = join(
    process.cwd(),
    '..',
    'fixtures',
    'scenarios',
    scenario,
    'principal.json',
  );
  const loaded: unknown = JSON.parse(readFileSync(path, 'utf8'));
  const responses: unknown = Reflect.get(Object(loaded), 'responses');
  const first: unknown = Array.isArray(responses) ? responses[0] : undefined;
  const body: unknown = Reflect.get(Object(first), 'body');
  const permissions: unknown = Reflect.get(Object(body), 'permissions');
  return {
    principalId: String(Reflect.get(Object(body), 'principal_id') ?? ''),
    displayName: String(Reflect.get(Object(body), 'display_name') ?? ''),
    email: null,
    roles: [],
    permissions: Array.isArray(permissions) ? (permissions as string[]) : [],
    teamNodeId: String(Reflect.get(Object(body), 'team_node_id') ?? ''),
    impersonating: false,
    impersonatedBy: null,
  };
}

/**
 * The principal body a viewer holding `permissions` would come back as.
 *
 * Built here rather than in each test because the console resolves the viewer
 * from `/auth/me` and from nowhere else — which is the property being relied on:
 * a role matrix that handed a screen a viewer object directly would prove
 * nothing about the console's own resolution.
 */
export function principalHolding(permissions: readonly string[]): unknown {
  return {
    principal_id: 'user-under-test',
    display_name: 'Avery Lockhart',
    email: null,
    kind: 'user',
    roles: [],
    permissions,
    team_node_id: 'org-northwind',
    impersonating: false,
    impersonated_by: null,
  };
}

/** One fixed instant, so a relative time in a test is a constant. */
export const NOW = new Date('2026-08-07T12:00:00.000Z');

/** The context a screen is rendered in, with everything but the viewer fixed. */
export function contextFor(
  viewer: Viewer,
  search: string | URLSearchParams = '',
): SurfaceContext {
  return {
    credential: 'a-token',
    locale: 'en',
    viewer,
    deployment: { name: 'HAL9000', timezone: 'UTC' },
    now: NOW,
    zone: 'UTC',
    search: typeof search === 'string' ? new URLSearchParams(search) : search,
  };
}
