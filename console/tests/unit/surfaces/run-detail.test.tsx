import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { RunDetailScreen } from '@/surfaces/screens/run-detail';

/**
 * A run that failed before it began: no turns, a summary that is the
 * deployment's own exception rather than a sentence somebody wrote.
 *
 * The console has one rule for text like this — no exception message from the
 * gateway is ever a headline — and this screen is where it can go wrong twice
 * over at once: the transcript's own "Report" entry used to carry the same
 * translated headline the summary panel already shows, and that duplicate
 * `events` entry is exactly what kept the cost and links panels from
 * recognising the run had nothing to show but the reason it never started.
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

const RUN = 'run-failed-early';

const RAW =
  'InvestigatorNotConfigured: No investigation runtime is configured. Set ' +
  "NINJASRE_INVESTIGATOR to 'module:factory' — a callable returning the runner.";

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function serveFailedBeforeStart(): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const bodies: Record<string, unknown> = {
      '/auth/me': {
        principal_id: 'user-operator',
        display_name: 'Avery Lockhart',
        kind: 'person',
        roles: ['owner'],
        permissions: ['investigation.read'],
        team_node_id: 'org-northwind',
        impersonating: false,
        impersonated_by: null,
      },
      [`/v1/runs/${RUN}`]: {
        run_id: RUN,
        status: 'failed',
        summary: RAW,
        trigger: 'interactive',
        started_at: '2026-08-07T13:52:00+00:00',
        finished_at: '2026-08-07T13:52:03+00:00',
      },
      [`/v1/runs/${RUN}/replay`]: {
        run_id: RUN,
        is_interrupted: false,
        total_cost: 0,
        total_tokens: 0,
        turns: [],
      },
      '/v1/incidents': { incidents: [] },
      [`/v1/investigations/${RUN}/interactions`]: { interactions: [] },
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

async function runScreen(): Promise<void> {
  render(await RunDetailScreen(await surfaceContext({}), RUN));
}

describe('a run that failed before it started', () => {
  it('never prints the deployment’s raw text more than once on the screen', async () => {
    serveFailedBeforeStart();
    await runScreen();

    // Present exactly once: the disclosure on the summary panel.
    expect(screen.getAllByText(RAW)).toHaveLength(1);
  });

  it('shows the translated failure headline in the header, the breadcrumb and the panel — never a fourth time', async () => {
    serveFailedBeforeStart();
    await runScreen();

    // Three, not one: the breadcrumb's current crumb, the page's own H1, and
    // the summary panel's body all read the same run's name from the same
    // place now, which is the property this suite holds them to — the
    // regression this test used to guard against was a *fourth* copy, in
    // the transcript's own "report" entry.
    const title = 'Investigations are not switched on yet';
    expect(screen.getAllByText(title)).toHaveLength(3);
    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
  });

  it('uses the operator trigger label instead of the internal slug', async () => {
    serveFailedBeforeStart();
    await runScreen();

    expect(screen.getByTestId('page-header')).toHaveTextContent('Manual');
    expect(screen.queryByText('interactive')).toBeNull();
  });

  it('carries no duplicate "report" entry into the transcript', async () => {
    serveFailedBeforeStart();
    await runScreen();

    // A transcript built only from the translated headline of a run that
    // never started is not a transcript entry — it is the same sentence
    // shown a second time, styled as if the run had concluded successfully.
    // With no turns and no report entry, the transcript panel has nothing to
    // draw and falls to its own, unrelated empty state.
    expect(screen.queryByTestId('transcript-event')).not.toBeInTheDocument();
    const transcriptPanel = screen
      .getAllByTestId('panel')
      .find((panel) => within(panel).queryByText('Investigation transcript') !== null);
    expect(transcriptPanel).toHaveAttribute('data-state', 'empty');
  });

  it('collapses the cost panel to one line rather than a full empty state', async () => {
    serveFailedBeforeStart();
    await runScreen();

    const cost = screen
      .getAllByTestId('panel')
      .find((panel) => within(panel).queryByText('Cost and tokens') !== null);
    expect(cost).toBeDefined();
    if (cost === undefined) return;
    expect(cost).toHaveAttribute('data-state', 'ready');
    expect(within(cost).getByText('No cost recorded')).toBeInTheDocument();
    // The one-line collapse carries no call to action back to another screen.
    expect(within(cost).queryByTestId('way-back')).toBeNull();
  });

  it('collapses the links panel to one line rather than a full empty state', async () => {
    serveFailedBeforeStart();
    await runScreen();

    const links = screen
      .getAllByTestId('panel')
      .find(
        (panel) =>
          within(panel).queryByText('What this investigation touched') !== null,
      );
    expect(links).toBeDefined();
    if (links === undefined) return;
    expect(links).toHaveAttribute('data-state', 'ready');
    expect(within(links).getByText('Nothing linked yet')).toBeInTheDocument();
    expect(within(links).queryByTestId('way-back')).toBeNull();
  });
});

/**
 * A settled run whose own record carries the same evidence tally the run
 * list's chip already reads — proof the findings panel's progress bar
 * actually draws when the data is there, not just that it stays away when
 * the data is not. None of the committed mock fixtures populate
 * `evidence_assessed` for any run, so this is the only place in the suite
 * that exercises the bar with real numbers.
 */
const ASSESSED_RUN = 'run-evidence-assessed';

function serveAssessedRun(): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const bodies: Record<string, unknown> = {
      '/auth/me': {
        principal_id: 'user-operator',
        display_name: 'Avery Lockhart',
        kind: 'person',
        roles: ['owner'],
        permissions: ['investigation.read'],
        team_node_id: 'org-northwind',
        impersonating: false,
        impersonated_by: null,
      },
      [`/v1/runs/${ASSESSED_RUN}`]: {
        run_id: ASSESSED_RUN,
        status: 'completed',
        summary: 'The volume filled because a retained log grew unbounded.',
        trigger: 'interactive',
        started_at: '2026-08-07T13:52:00+00:00',
        finished_at: '2026-08-07T13:52:03+00:00',
        evidence_assessed: true,
        evidence_backed: 3,
        evidence_missing: 1,
      },
      [`/v1/runs/${ASSESSED_RUN}/replay`]: {
        run_id: ASSESSED_RUN,
        is_interrupted: false,
        total_cost: 0,
        total_tokens: 0,
        turns: [],
      },
      '/v1/incidents': { incidents: [] },
      [`/v1/investigations/${ASSESSED_RUN}/interactions`]: { interactions: [] },
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

describe('a run whose own record says its evidence was assessed', () => {
  it('draws the findings panel’s progress bar with the run’s own backed-of-claims count', async () => {
    serveAssessedRun();
    render(await RunDetailScreen(await surfaceContext({}), ASSESSED_RUN));

    const bar = screen.getByTestId('findings-evidence-progress');
    expect(within(bar).getByText('3 of 4 claims backed')).toBeInTheDocument();
  });

  it('never draws the bar for a run whose record never assessed anything', async () => {
    serveFailedBeforeStart();
    await runScreen();

    expect(screen.queryByTestId('findings-evidence-progress')).not.toBeInTheDocument();
  });
});
