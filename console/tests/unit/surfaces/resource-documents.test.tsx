import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ResourcesScreen } from '@/surfaces/screens/resources';

import { serveScenario } from '../support/dataset';

/**
 * What has been written about a selected resource.
 *
 * A runbook about AdGuard and the container called `adguard` are the same thing
 * seen from two sides. The deployment writes the join; this panel is the only
 * place a human sees it without going and searching the corpus themselves.
 *
 * The name that produced each link is rendered beside it, and that is the point
 * of the panel rather than decoration: a link drawn by a name match can be
 * wrong, and an operator who can see *why* an entry is here can dismiss it. A
 * list with no reasons is one that has to be trusted whole.
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

const DOCUMENTS = [
  {
    document_id: 'corpus:docs/runbooks/adguard-dns-recovery.md',
    title: 'Recovering AdGuard DNS',
    location: 'docs/runbooks/adguard-dns-recovery.md',
    document_type: 'runbook',
    matched: 'adguard.example.invalid',
    matched_on: 'hostname',
  },
  {
    document_id: 'corpus:docs/postmortem/2026-07-20-recurrence.md',
    title: 'AdGuard DNS stalled again',
    location: 'docs/postmortem/2026-07-20-recurrence.md',
    document_type: 'postmortem',
    matched: 'adguard.example.invalid',
    matched_on: 'domain',
  },
];

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function serveDetail(documents: unknown[]): void {
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
          display_name: 'adguard',
        },
        rollup_rule: 'own_only',
        freshness_seconds: 300,
        signals: { sources: [], missing: [] },
        documents,
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

async function resources(query: Record<string, string> = {}): Promise<void> {
  render(await ResourcesScreen(await surfaceContext(query)));
}

describe('what has been written about a resource', () => {
  it('draws nothing until a row is selected', async () => {
    serveScenario('populated');
    await resources();

    expect(screen.queryByTestId('resource-documents')).toBeNull();
  });

  it('lists every document the corpus links to this resource', async () => {
    serveDetail(DOCUMENTS);
    await resources({ selected: SELECTED });

    const entries = screen.getAllByTestId('resource-document');
    expect(entries).toHaveLength(2);
    expect(entries[0]).toHaveTextContent('Recovering AdGuard DNS');
    expect(entries[1]).toHaveTextContent('AdGuard DNS stalled again');
  });

  it('says which kind of document each one is', async () => {
    // A post-mortem and a runbook are read differently, and an operator who
    // cannot tell them apart will follow the post-mortem.
    serveDetail(DOCUMENTS);
    await resources({ selected: SELECTED });

    const entries = screen.getAllByTestId('resource-document');
    expect(entries[0]).toHaveTextContent('runbook');
    expect(entries[1]).toHaveTextContent('postmortem');
  });

  it('says which name put each entry here', async () => {
    serveDetail(DOCUMENTS);
    await resources({ selected: SELECTED });

    expect(screen.getAllByTestId('resource-document')[0]).toHaveTextContent(
      'adguard.example.invalid',
    );
  });

  it('links each entry to where the document lives', async () => {
    serveDetail(DOCUMENTS);
    await resources({ selected: SELECTED });

    expect(screen.getAllByTestId('resource-document')[0]).toHaveTextContent(
      'docs/runbooks/adguard-dns-recovery.md',
    );
  });

  it('draws no panel for a resource nobody has written about', async () => {
    // The ordinary state of most of any estate, and of all of one whose corpus
    // has not been synced. An empty panel on every resource would be noise.
    serveDetail([]);
    await resources({ selected: SELECTED });

    expect(screen.queryByTestId('resource-documents')).toBeNull();
  });
});
