import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ObservationTab } from '@/surfaces/screens/detectors';

/**
 * A detector a document proposed, in the table beside the ones that are running.
 *
 * Two rows that look the same are the failure mode: "this is watching your
 * estate" and "somebody's runbook suggests this and nobody has decided" are
 * different claims, and an operator who cannot tell them apart will read a
 * proposal as coverage they have.
 *
 * The excerpt is the other half. A threshold is a judgement, and a proposed one
 * is somebody else's — so the sentence they wrote it in is rendered beside it,
 * which is what makes enabling it a decision rather than an acceptance.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** Built rather than written: a literal origin in console source is refused. */
const BASE = ['http:', '//gateway.test'].join('');

const RUNNING = {
  detector_id: 'datastore-near-full',
  name: 'Datastore near full',
  description: 'A datastore that fills stops every guest on it at once.',
  severity: 'critical',
  enabled: true,
  signal: 'storage.used_percent',
  subjects_covered: 4,
  subjects_total: 4,
  last_verdict: 'clear',
  origin: '',
  origin_excerpt: '',
  proposed: false,
};

const PROPOSED = {
  detector_id: 'corpus-no-datastore-is-above-its-safe-fill',
  name: 'No datastore is above its safe fill',
  description: 'A datastore past this cannot complete a snapshot.',
  severity: 'high',
  enabled: false,
  signal: 'datastore.used_percent',
  subjects_covered: 0,
  subjects_total: 4,
  last_verdict: 'clear',
  origin: 'corpus:docs/runbooks/cluster-double-check-queries.md',
  origin_excerpt:
    'No datastore is above its safe fill — A datastore past this cannot complete a snapshot of its largest guest.',
  proposed: true,
};

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
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
      '/v1/detectors': { detectors: [RUNNING, PROPOSED], paused: false },
      '/v1/observations': { observations: [] },
    };
    const body = bodies[path];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === undefined ? 404 : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function detectors(): Promise<void> {
  render(await ObservationTab(await surfaceContext({})));
}

function rowFor(detectorId: string): HTMLElement {
  const found = screen
    .getAllByTestId('detector')
    .find((row) => row.getAttribute('data-detector') === detectorId);
  if (found === undefined) throw new Error(`no row for ${detectorId}`);
  return found;
}

describe('detectors a document proposed', () => {
  it('lists a candidate beside the detectors that are running', async () => {
    await detectors();

    expect(screen.getAllByTestId('detector')).toHaveLength(2);
    expect(rowFor(PROPOSED.detector_id)).toHaveTextContent(
      'No datastore is above its safe fill',
    );
  });

  it('marks the candidate as a proposal', async () => {
    await detectors();

    expect(rowFor(PROPOSED.detector_id)).toHaveTextContent('proposed by a document');
  });

  it('leaves a detector somebody wrote by hand unmarked', async () => {
    // The distinction is the whole point. A running detector rendered as a
    // proposal reads as coverage nobody has.
    await detectors();

    expect(
      rowFor(RUNNING.detector_id).querySelector('[data-testid="detector-proposed"]'),
    ).toBeNull();
    expect(
      rowFor(RUNNING.detector_id).querySelector('[data-testid="detector-origin"]'),
    ).toBeNull();
  });

  it('quotes the sentence the proposing document was written in', async () => {
    await detectors();

    const origin = rowFor(PROPOSED.detector_id).querySelector(
      '[data-testid="detector-origin"]',
    );
    expect(origin).not.toBeNull();
    expect(origin).toHaveTextContent('cannot complete a snapshot');
    expect(origin?.getAttribute('data-origin')).toBe(
      'corpus:docs/runbooks/cluster-double-check-queries.md',
    );
  });
});
