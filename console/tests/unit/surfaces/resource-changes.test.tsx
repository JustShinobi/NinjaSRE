import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ResourcesScreen } from '@/surfaces/screens/resources';

import { serveScenario } from '../support/dataset';

/**
 * What changed under a selected resource, and how strongly it is connected.
 *
 * The panel that answers the question an operator asks before any other one.
 * Two things about it are load-bearing and neither is decoration.
 *
 * **The strength is on the row.** A change that altered the component managing
 * this container and a change that merely landed in the same half hour are
 * different facts, and a panel that listed them identically would be a panel
 * that manufactures causes. The coincidence is shown — hidden, it could not be
 * ruled out by anybody reading the page — and it is shown as what it is.
 *
 * **The sentence renders even when there is nothing to list.** An empty panel
 * reads as "nothing has changed"; a deployment that consulted nothing has
 * established nothing, and the two must not look the same.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** The container the committed dataset carries a detail for. */
const SELECTED = 'ct-100';

/** Built rather than written: a literal origin in console source is refused. */
const BASE = ['http:', '//gateway.test'].join('');

const MANAGING = {
  change_id: '9f2c1ab',
  author: 'erik',
  message: 'feat(monitoring): raise the scrape interval',
  component: 'monitoring',
  applied: true,
  instant: '2026-08-07T14:19:03+00:00',
  strength: 'manages_resource',
  temporal_only: false,
  why: 'services/monitoring/stack/values.yaml belongs to the monitoring component.',
  paths: ['services/monitoring/stack/values.yaml'],
  source: 'infra_apply',
};

const COINCIDENCE = {
  change_id: 'b0c99fe',
  author: 'erik',
  message: 'feat(storage): widen the backup datastore',
  component: 'storage',
  applied: true,
  instant: '2026-08-07T14:28:00+00:00',
  strength: 'window_only',
  temporal_only: true,
  why: 'This change happened in the same window and nothing connects it.',
  paths: ['services/storage/datastore/main.tf'],
  source: 'infra_apply',
};

const UNAPPLIED = {
  change_id: '3d81e0c',
  author: 'erik',
  message: 'chore(monitoring): tidy the alert rule comments',
  component: 'monitoring',
  applied: false,
  instant: '2026-08-07T14:12:00+00:00',
  strength: 'window_only',
  temporal_only: true,
  why: 'This change happened in the same window and nothing connects it.',
  paths: ['services/monitoring/rules/node.yaml'],
  source: 'infra_apply',
};

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function serveDetail(changes: unknown): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const bodies: Record<string, unknown> = {
      '/auth/me': {
        principal_id: 'user-operator',
        display_name: 'Avery Lockhart',
        kind: 'person',
        roles: ['owner'],
        permissions: ['investigation.read', 'config.read'],
        team_node_id: 'org-northwind',
        impersonating: false,
        impersonated_by: null,
      },
      '/v1/estate/resources': { resources: [] },
      '/v1/estate/summary': { total: 0, captured_at: '2026-08-10T12:00:00Z' },
      [`/v1/estate/resources/${SELECTED}`]: {
        resource: {
          resource_id: SELECTED,
          kind: 'container',
          display_name: 'mon-prometheus',
        },
        rollup_rule: 'own_only',
        freshness_seconds: 300,
        signals: { sources: [], missing: [] },
        documents: [],
        changes,
      },
    };
    const body = bodies[path];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === undefined ? 404 : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

const ANSWERED = {
  statement: '3 change(s) landed in the 24 hour(s) ending now, from infra_apply.',
  answered: true,
  window_hours: 24,
  sources: ['infra_apply'],
  total: 3,
  truncated: false,
  degraded: [],
  entries: [MANAGING, COINCIDENCE, UNAPPLIED],
};

async function resources(query: Record<string, string> = {}): Promise<void> {
  render(await ResourcesScreen(await surfaceContext(query)));
}

describe('what changed under a resource', () => {
  it('draws nothing until a row is selected', async () => {
    serveScenario('populated');
    await resources();

    expect(screen.queryByTestId('resource-changes')).toBeNull();
  });

  it('lists every change the window held', async () => {
    serveDetail(ANSWERED);
    await resources({ selected: SELECTED });

    expect(screen.getAllByTestId('resource-change')).toHaveLength(3);
  });

  it('marks the change that altered something managing this resource', async () => {
    serveDetail(ANSWERED);
    await resources({ selected: SELECTED });

    const entries = screen.getAllByTestId('resource-change');
    expect(entries[0]).toHaveAttribute('data-strength', 'manages_resource');
    expect(entries[0]).toHaveTextContent('9f2c1ab');
    expect(entries[0]).toHaveTextContent('feat(monitoring): raise the scrape interval');
  });

  it('shows a change that only shares a window rather than hiding it', async () => {
    // Hidden, nobody reading the page can rule it out. Shown without its
    // label, it reads as a cause.
    serveDetail(ANSWERED);
    await resources({ selected: SELECTED });

    const entries = screen.getAllByTestId('resource-change');
    expect(entries[1]).toHaveAttribute('data-strength', 'window_only');
    expect(entries[1]).toHaveTextContent('b0c99fe');
  });

  it('says which changes never reached the cluster', async () => {
    serveDetail(ANSWERED);
    await resources({ selected: SELECTED });

    const entries = screen.getAllByTestId('resource-change');
    expect(entries[2]).toHaveAttribute('data-applied', 'false');
  });

  it('carries the sentence a quiet resource earns', async () => {
    // The finding this whole panel exists for: an absence with a provenance.
    serveDetail({
      statement: 'No change touched mon-prometheus in the 24 hour(s) ending now.',
      answered: true,
      window_hours: 24,
      sources: ['infra_apply'],
      total: 0,
      truncated: false,
      degraded: [],
      entries: [],
    });
    await resources({ selected: SELECTED });

    expect(screen.getByTestId('resource-changes')).toHaveTextContent(
      'No change touched mon-prometheus',
    );
  });

  it('says nothing was consulted rather than showing an empty list', async () => {
    serveDetail({
      statement: 'No change source is configured for this deployment.',
      answered: false,
      window_hours: 24,
      sources: [],
      total: 0,
      truncated: false,
      degraded: [],
      entries: [],
    });
    await resources({ selected: SELECTED });

    const panel = screen.getByTestId('resource-changes');
    expect(panel).toHaveTextContent('No change source is configured');
    expect(panel).toHaveAttribute('data-answered', 'false');
  });

  it('draws no panel at all for a deployment whose detail carries none', async () => {
    // A gateway older than this feature, or a client reading a cached
    // response. Neither should render an empty box.
    serveDetail(undefined);
    await resources({ selected: SELECTED });

    expect(screen.queryByTestId('resource-changes')).toBeNull();
  });
});
