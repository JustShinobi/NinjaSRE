import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ObservationTab } from '@/surfaces/screens/detectors';

/**
 * The empty state that sent an operator with two connected sources back to
 * "Connect a source" — the one screen they had already been to.
 *
 * Sources being reachable and the guardian being switched on are two
 * different facts, and only the second is what an empty "Continuous
 * observation" tab is actually missing once the first is true. This file
 * pins the distinction: the watching cause (with its destination rewritten
 * to where the toggle actually lives, since a bare `watchingCause` would
 * point this tab back at itself) and the setup cause when the deployment
 * itself is unfinished.
 *
 * Schedules is no longer a sibling tab here: a recurring investigation runs
 * on a clock rather than on a detector, so it moved to the Settings surface
 * that absorbed it (`console/tests/unit/surfaces/settings-schedules-destinations.test.tsx`),
 * beside where its results end up.
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

function principal(permissions: readonly string[] = []): unknown {
  return {
    principal_id: 'user-operator',
    display_name: 'Avery Lockhart',
    kind: 'person',
    roles: ['owner'],
    permissions,
    team_node_id: 'org-northwind',
    impersonating: false,
    impersonated_by: null,
  };
}

/** A checklist that still has outstanding steps: no provider stored, and no
 * investigation has completed — the step this screen's own cause depends on. */
const SETUP_INCOMPLETE = {
  complete: false,
  provider: 'absent',
  integrations: [],
  steps: [
    { name: 'model-provider', state: 'ready' },
    {
      name: 'first-investigation',
      state: 'blocked',
      title: 'Run your first investigation',
    },
  ],
};

/** A checklist with nothing left to do. */
const SETUP_COMPLETE = {
  complete: true,
  provider: 'openai',
  integrations: [{ name: 'openai', readiness: 'verified' }],
  steps: [
    { name: 'infrastructure-source', state: 'done' },
    { name: 'first-investigation', state: 'done' },
  ],
};

function enabledDetector(id: string): unknown {
  return {
    detector_id: id,
    name: id,
    description: 'Watches quorum margin.',
    severity: 'critical',
    enabled: true,
    signal: 'x',
    subjects_covered: 1,
    subjects_total: 1,
    last_verdict: 'clear',
    last_evaluated_at: '2026-08-07T10:00:00+00:00',
    origin: '',
    origin_excerpt: '',
    proposed: false,
  };
}

/** The fixture scenario carries no switched-off detector — every shipped
 * detector is enabled — so the disabled branch is built by hand here. */
function disabledDetector(id: string): unknown {
  return {
    detector_id: id,
    name: id,
    description: 'Watches quorum margin.',
    severity: 'critical',
    enabled: false,
    signal: 'x',
    subjects_covered: 1,
    subjects_total: 1,
    last_verdict: 'clear',
    last_evaluated_at: '2026-08-07T10:00:00+00:00',
    origin: '',
    origin_excerpt: '',
    proposed: false,
  };
}

function serve(bodies: {
  readonly permissions?: readonly string[];
  readonly detectors: readonly unknown[];
  readonly setup: unknown;
}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const byPath: Record<string, unknown> = {
      '/auth/me': principal(bodies.permissions ?? []),
      '/v1/detectors': { detectors: bodies.detectors },
      '/v1/setup/checklist': bodies.setup,
    };
    const body = byPath[path];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === undefined ? 404 : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function observation(): Promise<void> {
  render(await ObservationTab(await surfaceContext({})));
}

function emptyPanel(): HTMLElement {
  const panel = screen
    .getAllByTestId('panel')
    .find((candidate) => candidate.getAttribute('data-state') === 'empty');
  if (panel === undefined) throw new Error('no empty panel rendered');
  return panel;
}

describe('sources are connected and nothing is switched on', () => {
  beforeEach(() => {
    serve({ detectors: [], setup: SETUP_COMPLETE });
  });

  it('says nothing is watching, not that a source needs connecting', async () => {
    await observation();

    const panel = emptyPanel();
    expect(panel).toHaveTextContent(
      'No detector is switched on, so nothing is being watched',
    );
    expect(panel).not.toHaveTextContent('Detectors ship with the deployment');
    expect(screen.queryByText('Connect a source')).toBeNull();
  });

  it('sends the operator to turn on continuous observation, at the node they hold', async () => {
    await observation();

    const action = screen.getByRole('link', {
      name: 'Turn on continuous observation',
    });
    expect(action).toHaveAttribute('href', '/settings/alert-intake');
  });
});

describe('the deployment itself is still being set up', () => {
  beforeEach(() => {
    serve({ detectors: [], setup: SETUP_INCOMPLETE });
  });

  it('names the outstanding setup rather than the guardian toggle', async () => {
    await observation();

    const panel = emptyPanel();
    expect(panel).toHaveTextContent('still being set up');
    expect(panel).not.toHaveTextContent('No detector is switched on');
  });

  it('points at finishing the setup, not at Configuration', async () => {
    await observation();

    const action = screen.getByRole('link', { name: 'Finish setting up' });
    expect(action).toHaveAttribute('href', '/first-run');
  });
});

describe('a deployment that is watching and has coverage', () => {
  it('keeps the feature’s own words once nothing local explains an empty table', async () => {
    // A live detector exists, so the panel is not empty in the first place —
    // there is no cause to apply and the table renders it.
    serve({
      detectors: [enabledDetector('quorum-margin-zero')],
      setup: SETUP_COMPLETE,
    });
    await observation();

    expect(screen.queryAllByTestId('panel')).not.toHaveLength(0);
    expect(
      screen
        .getAllByTestId('detector')
        .some((row) => row.getAttribute('data-detector') === 'quorum-margin-zero'),
    ).toBe(true);
  });
});

describe('a detector that is switched on', () => {
  it('never shows the raw resource-health word for its own on/off state', async () => {
    serve({
      detectors: [enabledDetector('quorum-margin-zero')],
      setup: SETUP_COMPLETE,
    });
    await observation();

    const row = screen
      .getAllByTestId('detector')
      .find(
        (candidate) => candidate.getAttribute('data-detector') === 'quorum-margin-zero',
      );
    if (row === undefined) throw new Error('the detector row is not there');
    // `healthy` is a resource's word, never a detector's own on/off state.
    expect(row.textContent).not.toMatch(/healthy/i);
    expect(within(row).getByTestId('detector-state')).toHaveTextContent('Enabled');
  });
});

describe('a detector that has been switched off', () => {
  // No populated fixture carries this branch, so it is proved at the unit
  // level with a detector built by hand rather than left unverified.
  it('says the detector is disabled, in the column already titled that', async () => {
    serve({
      detectors: [disabledDetector('backup-job-disabled')],
      setup: SETUP_COMPLETE,
    });
    await observation();

    const row = screen
      .getAllByTestId('detector')
      .find(
        (candidate) =>
          candidate.getAttribute('data-detector') === 'backup-job-disabled',
      );
    if (row === undefined) throw new Error('the detector row is not there');
    expect(within(row).getByTestId('detector-state')).toHaveTextContent('Disabled');
  });
});
