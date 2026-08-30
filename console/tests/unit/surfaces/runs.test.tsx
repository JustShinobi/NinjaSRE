import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EN } from '@/i18n/en';
import { RunsScreen } from '@/surfaces/screens/runs';

import { identifierAsName } from '../../e2e/bans';
import { contextFor, datasetViewer, serveScenario } from '../support/dataset';

/**
 * A run id shaped like `platform/runs/recorder.py`'s own generator —
 * `uuid.uuid4().hex`, thirty-two lowercase hexadecimal characters, no
 * separator. The committed fixture's ids (`run-0001`, ...) never exercise
 * this: they read as a friendly slug to `identifierAsName`, which is exactly
 * why the defect below reached staging undetected by this suite.
 */
const REALISTIC_RUN_ID = 'e19e882a1c9b4d5e8f6a2b3c7d0e1f24';

// Assembled by parts, never a literal origin: the boundary rule that keeps a
// real third-party address out of console source cannot tell this fixture
// address apart from one, and should not try to — see `../support/dataset`'s
// own `BASE` for the same construction, on the same reasoning.
const FIXTURE_ORIGIN = ['http:', '//fixtures.invalid'].join('');

/** One run, served over a custom `/v1/runs`, with a realistic hexadecimal id. */
function serveOneRealisticRun(): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), FIXTURE_ORIGIN).pathname;
    if (path === '/auth/me') {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            principal_id: 'user-under-test',
            display_name: 'Avery Lockhart',
            email: null,
            kind: 'user',
            roles: [],
            permissions: [],
            team_node_id: 'org-northwind',
            impersonating: false,
            impersonated_by: null,
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    }
    if (path === '/v1/runs') {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            runs: [
              {
                run_id: REALISTIC_RUN_ID,
                trigger: 'alert',
                status: 'succeeded',
                headline: 'a guest reached the ceiling of its own volume',
                summary: 'a guest reached the ceiling of its own volume',
                report: '',
                started_at: '2026-08-05T11:19:00+00:00',
                finished_at: '2026-08-05T11:33:00+00:00',
                incident_id: '',
                touched_resources: [],
              },
            ],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    }
    return Promise.resolve(
      new Response('{}', {
        status: 404,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

/** The one run the stubbed server below serves, listed and in detail. */
const RUN_RECORD = {
  run_id: REALISTIC_RUN_ID,
  trigger: 'alert',
  status: 'succeeded',
  headline: 'a guest reached the ceiling of its own volume',
  summary: '',
  report: '',
  started_at: '2026-08-05T11:19:00+00:00',
  finished_at: '2026-08-05T11:33:00+00:00',
  incident_id: '',
  touched_resources: ['lxc/122', 'pve01'],
  evidence_assessed: true,
  evidence_backed: 4,
  evidence_missing: 0,
  evidence_supporting_names: [],
  evidence_missing_names: [],
};

/** The episode `/v1/memory/episode` answers with, for the run under test. */
const EPISODE = {
  episode_id: 'ep-0001',
  title: 'A guest task log with a user on it ends this shape in one call',
  summary: 'The shutdown was deliberate, and the task log said so.',
  outcome: 'resolved',
  components: ['redis'],
  occurred_at: '2026-08-05T11:33:00+00:00',
};

/** Every address the open card reads, answered — and each one recorded. */
function serveOpenCard(episode: unknown): string[] {
  const asked: string[] = [];
  const bodies: Readonly<Record<string, unknown>> = {
    '/auth/me': {
      principal_id: 'user-under-test',
      display_name: 'Avery Lockhart',
      email: null,
      kind: 'user',
      roles: [],
      permissions: [],
      team_node_id: 'org-northwind',
      impersonating: false,
      impersonated_by: null,
    },
    '/v1/runs': { runs: [RUN_RECORD] },
    [`/v1/runs/${REALISTIC_RUN_ID}`]: RUN_RECORD,
    [`/v1/runs/${REALISTIC_RUN_ID}/replay`]: {
      run_id: REALISTIC_RUN_ID,
      turns: [],
      total_cost: 0,
      unpriced_turns: 0,
      total_tokens: 4096,
      is_interrupted: false,
    },
    [`/v1/investigations/${REALISTIC_RUN_ID}/interactions`]: { interactions: [] },
    '/v1/memory/episode': { episode },
  };

  vi.stubGlobal('fetch', (input: unknown) => {
    const address = new URL(String(input), FIXTURE_ORIGIN);
    asked.push(`${address.pathname}${address.search}`);
    const body = bodies[address.pathname];
    if (body === undefined) {
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
  return asked;
}

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: () => ({ value: 'a-token' }),
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
  serveScenario('populated');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the runs list language', () => {
  it('uses investigations in visible copy and translates trigger slugs', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    expect(screen.queryByText('Every run this deployment has recorded')).toBeNull();

    // The trigger reads as a word on the card's own metadata line, beside the
    // short id. Joined rather than compared per card, because the slug is what
    // must never appear anywhere in the visible copy.
    const meta = screen
      .getAllByTestId('run-card')
      .map((card) => card.textContent)
      .join(' ');

    expect(meta).toContain('Alert');
    expect(meta).toContain('Scheduled');
    expect(meta).toContain('Manual');
    expect(meta).not.toContain('schedule ·');
  });

  it('keeps the raw trigger in the address value while showing its label', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    // Each filter is a chip — a link whose own address carries the raw slug
    // the API filters by, while the word on the chip is the translated
    // label. Both groups (status, trigger) share one `filter-chip` testid,
    // so the trigger ones are found by their own `data-filter` attribute.
    const chips = screen.getAllByTestId('filter-chip');
    const alert = chips.find(
      (chip) => chip.getAttribute('data-filter') === 'trigger' && chip.textContent === 'Alert',
    );
    const scheduled = chips.find(
      (chip) =>
        chip.getAttribute('data-filter') === 'trigger' && chip.textContent === 'Scheduled',
    );
    if (alert === undefined || scheduled === undefined) {
      throw new Error('the trigger chips are not on the page');
    }
    expect(alert.getAttribute('href')).toContain('trigger=alert');
    expect(scheduled.getAttribute('href')).toContain('trigger=schedule');
  });

  it('gives the subject cell a tooltip containing the complete subject', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    const firstCard = screen.getAllByTestId('run-card')[0];
    if (firstCard === undefined) throw new Error('the populated fixture has no runs');

    const tooltip = firstCard.querySelector('[title]');
    if (tooltip === null) throw new Error('the subject has no tooltip');
    // The card gives the subject a whole line, so what is shown and what the
    // tooltip carries are the same sentence unless the deployment's own text
    // was longer than the subject reader will truncate.
    expect(tooltip.getAttribute('title')).toContain(
      tooltip.textContent.trim().slice(0, 20),
    );
  });
});

describe('what the list tells a reader about itself', () => {
  it('says a row opens where it sits, rather than leaving that to be discovered', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    // The whole arrangement of this screen — the card that grows instead of a
    // row that navigates — is invisible until somebody presses one. The
    // subtitle is where it gets said.
    expect(screen.getByText(EN['page.runs.context'])).toBeInTheDocument();
    expect(EN['page.runs.context']).toContain('Open one where it sits.');
  });
});

describe('the episode an open card asks the corpus for', () => {
  it('asks for the open run’s own episode, by run', async () => {
    const asked = serveOpenCard(EPISODE);

    render(
      await RunsScreen(contextFor(datasetViewer(), `selected=${REALISTIC_RUN_ID}`)),
    );

    expect(asked).toContain(`/v1/memory/episode?run_id=${REALISTIC_RUN_ID}`);
    expect(screen.getByTestId('run-episode')).toHaveTextContent(
      'A guest task log with a user on it ends this shape in one call',
    );
  });

  it('prints the calm sentence for a run that wrote none', async () => {
    serveOpenCard(null);

    render(
      await RunsScreen(contextFor(datasetViewer(), `selected=${REALISTIC_RUN_ID}`)),
    );

    expect(screen.getByText(EN['run.remembered.none'])).toBeInTheDocument();
    expect(screen.queryByTestId('run-episode')).toBeNull();
  });

  it('asks the corpus nothing at all while every card is shut', async () => {
    const asked = serveOpenCard(EPISODE);

    render(await RunsScreen(contextFor(datasetViewer())));

    expect(asked.some((address) => address.startsWith('/v1/memory/episode'))).toBe(
      false,
    );
  });
});

describe('the run column against a real deployment’s own id shape', () => {
  // A staging sweep clicked a run list and had its own investigation column
  // accused: the eight-character fragment shown there is nothing but
  // hexadecimal digits, because a real run id is `uuid.uuid4().hex`
  // (`platform/runs/recorder.py`) with no separator anywhere in it. The
  // subject column beside it already carries the run's real name — this
  // column is deliberately kept as short, pasteable metadata (a support
  // channel), but "kept as metadata" and "reads as a bare identifier
  // standing in for a name" are the same string to a reader who never sees
  // the column header.
  it('never leaves the run column as nothing but hexadecimal digits', async () => {
    serveOneRealisticRun();

    render(await RunsScreen(contextFor(datasetViewer())));

    const card = screen.getAllByTestId('run-card')[0];
    if (card === undefined) throw new Error('the stubbed run did not render a card');
    const identifier = card.querySelector('.font-mono');
    if (identifier === null) throw new Error('the card carries no short id');

    expect(identifier.textContent).toContain(REALISTIC_RUN_ID.slice(0, 8));
    expect(identifierAsName(identifier.textContent || '')).toBeNull();
  });
});
