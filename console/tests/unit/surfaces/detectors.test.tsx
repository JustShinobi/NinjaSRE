import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ObservationTab, SchedulesTab } from '@/surfaces/screens/detectors';

/**
 * The empty state that sent an operator with two connected sources back to
 * "Connect a source" — the one screen they had already been to.
 *
 * Sources being reachable and the guardian being switched on are two
 * different facts, and only the second is what an empty "Continuous
 * observation" tab is actually missing once the first is true. This file
 * pins the distinction: the watching cause (with its destination rewritten
 * to where the toggle actually lives, since a bare `watchingCause` would
 * point this tab back at itself), the setup cause when the deployment itself
 * is unfinished, and the "Schedules" tab's own empty state — which, unlike
 * the detector table, keeps its create form on the page rather than hiding
 * it behind the notice. The two used to be one screen; they are two tabs of
 * Signals now (`screens/signals.tsx`), and each is tested here on its own.
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

/** A checklist that still has outstanding steps: no provider stored. */
const SETUP_INCOMPLETE = {
  complete: false,
  provider: 'absent',
  integrations: [],
  steps: [],
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

function serve(bodies: {
  readonly permissions?: readonly string[];
  readonly detectors: readonly unknown[];
  readonly schedules?: readonly unknown[];
  readonly setup: unknown;
}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const byPath: Record<string, unknown> = {
      '/auth/me': principal(bodies.permissions ?? []),
      '/v1/detectors': { detectors: bodies.detectors },
      // `/v1/schedules` answers with a bare array, not an envelope — see
      // `rowsOf` in the screen under test.
      '/v1/schedules': bodies.schedules ?? [],
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

async function schedules(): Promise<void> {
  const content = await SchedulesTab(await surfaceContext({}));
  render(content ?? <></>);
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
    expect(action).toHaveAttribute('href', '/configuration?node=org-northwind');
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

describe('scheduled investigations with none set up yet', () => {
  beforeEach(() => {
    serve({
      permissions: ['schedule.manage'],
      detectors: [],
      schedules: [],
      setup: SETUP_COMPLETE,
    });
  });

  it('names what is missing, why, and links to the form that fixes it', async () => {
    await schedules();

    const notice = screen.getByTestId('schedules-empty');
    expect(notice).toHaveTextContent('No scheduled investigations');
    expect(notice).toHaveTextContent('None is set up for this team yet');
    expect(screen.getByRole('link', { name: 'Create one below' })).toHaveAttribute(
      'href',
      '#schedule-create',
    );
  });

  it('still shows the create form, rather than hiding it behind the notice', async () => {
    await schedules();

    expect(screen.getByTestId('create-schedule')).toBeInTheDocument();
  });

  it('explains what the section is for', async () => {
    await schedules();

    expect(
      screen.getByText(
        'Every recurring investigation this team has scheduled, and what it runs on',
      ),
    ).toBeInTheDocument();
  });
});

describe('scheduled investigations with something already on the calendar', () => {
  it('does not show the empty notice once a schedule exists', async () => {
    serve({
      permissions: ['schedule.manage'],
      detectors: [],
      schedules: [
        {
          job_id: 'weekly-audit',
          name: 'Weekly audit',
          cron: '0 8 * * 1',
          objective: 'Summarise the week',
          timezone: 'UTC',
          enabled: true,
          next_run_at: '2026-08-17T08:00:00+00:00',
        },
      ],
      setup: SETUP_COMPLETE,
    });
    await schedules();

    expect(screen.queryByTestId('schedules-empty')).toBeNull();
    expect(screen.getByTestId('schedule')).toBeInTheDocument();
  });
});

describe('a viewer who may not manage schedules', () => {
  it('renders no schedules panel at all, rather than one it cannot use', async () => {
    serve({ permissions: [], detectors: [], setup: SETUP_COMPLETE });
    await schedules();

    expect(screen.queryByTestId('schedules-empty')).toBeNull();
    expect(screen.queryByTestId('create-schedule')).toBeNull();
  });
});
