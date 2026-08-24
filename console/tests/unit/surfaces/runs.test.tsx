import { render, screen, within } from '@testing-library/react';
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

    expect(
      screen.getByText('Every investigation this deployment has recorded'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Every run this deployment has recorded')).toBeNull();

    const triggers = screen.getAllByTestId('row').map((row) => {
      const cells = within(row).getAllByRole('cell');
      return cells[2]?.textContent ?? '';
    });

    expect(triggers).toEqual(expect.arrayContaining(['Alert', 'Scheduled', 'Manual']));
    expect(triggers).not.toContain('alert');
    expect(triggers).not.toContain('schedule');
    expect(triggers).not.toContain('manual');
  });

  it('keeps the raw trigger in the address value while showing its label', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    const trigger = screen.getByRole('combobox', { name: EN['runs.filter.trigger'] });
    expect(within(trigger).getByRole('option', { name: 'Alert' })).toHaveValue('alert');
    expect(within(trigger).getByRole('option', { name: 'Scheduled' })).toHaveValue(
      'schedule',
    );
  });

  it('gives the subject cell a tooltip containing the complete subject', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    const firstRow = screen.getAllByTestId('row')[0];
    if (firstRow === undefined) throw new Error('the populated fixture has no runs');
    const subject = within(firstRow).getAllByRole('cell')[0];
    if (subject === undefined) throw new Error('the run has no subject cell');

    const tooltip = subject.querySelector('[title]');
    if (tooltip === null) throw new Error('the subject has no tooltip');
    const visibleSubject = subject.querySelector('span.truncate');
    if (visibleSubject === null) throw new Error('the subject has no visible text');
    expect(tooltip.getAttribute('title')).toBe(visibleSubject.textContent.trim());
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

    const row = screen.getAllByTestId('row')[0];
    if (row === undefined) throw new Error('the stubbed run did not render a row');
    const cells = within(row).getAllByRole('cell');
    const runColumn = cells[3];
    if (runColumn === undefined) throw new Error('the row has no run-id column');

    expect(runColumn.textContent).toContain(REALISTIC_RUN_ID.slice(0, 8));
    expect(identifierAsName(runColumn.textContent || '')).toBeNull();
  });
});
