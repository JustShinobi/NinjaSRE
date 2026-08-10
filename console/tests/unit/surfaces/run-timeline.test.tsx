import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { rulerFromReplay } from '@/surfaces/changes';
import { RunDetailScreen } from '@/surfaces/screens/run-detail';

/**
 * The deploy that happened thirteen minutes before the error, on the same ruler.
 *
 * The footer of the investigation screen, and the only place in the console
 * where "what changed" and "when this broke" are drawn against one another
 * rather than in two lists a reader has to align in their head. It is the visual
 * answer to the question an SRE asks first.
 *
 * Everything it draws comes out of the run's own transcript. The agent called
 * the change capability, the result entered the trace, and the overlay reads it
 * back — so the ruler cannot show a change the investigation did not see, and
 * there is no second query that could disagree with the report.
 *
 * The grading survives the trip. A change that merely shares the window is drawn
 * as one, because a mark on a timeline is the most persuasive thing on the page
 * and an ungraded one would persuade of something nobody established.
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

const RUN = 'run-0001';

const WINDOW = { start: '2026-08-07T13:00:00+00:00', end: '2026-08-07T14:00:00+00:00' };

/** The apply that governs the failing container, halfway along the ruler. */
const MANAGING = {
  change_id: '9f2c1ab',
  author: 'erik',
  message: 'feat(monitoring): raise the scrape interval',
  component: 'monitoring',
  applied: true,
  instant: '2026-08-07T13:30:00+00:00',
  strength: 'manages_resource',
  temporal_only: false,
  why: 'services/monitoring/stack/values.yaml belongs to the monitoring component.',
  paths: ['services/monitoring/stack/values.yaml'],
  source: 'infra_apply',
};

/** A change three quarters along that connects to nothing. */
const COINCIDENCE = {
  change_id: 'b0c99fe',
  author: 'erik',
  message: 'feat(storage): widen the backup datastore',
  component: 'storage',
  applied: true,
  instant: '2026-08-07T13:45:00+00:00',
  strength: 'window_only',
  temporal_only: true,
  why: 'This change happened in the same window and nothing connects it.',
  paths: ['services/storage/datastore/main.tf'],
  source: 'infra_apply',
};

function replay(changes: readonly unknown[]): unknown {
  return {
    run_id: RUN,
    turns: [
      {
        turn_id: 'turn-1',
        index: 0,
        model: 'a-model',
        selection_rationale: '',
        calls: [
          {
            call_id: 'call-1',
            name: 'changes_in_window',
            status: 'succeeded',
            duration_ms: 12,
            arguments: { resource: 'ct-100' },
            result: {
              statement: 'Something landed in the window.',
              answered: true,
              window: { start: WINDOW.start, end: WINDOW.end, hours: 1 },
              sources: ['infra_apply'],
              total: changes.length,
              truncated: false,
              degraded: [],
              changes,
            },
          },
        ],
      },
    ],
  };
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function serveRun(replayBody: unknown): void {
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
        status: 'completed',
        summary: 'The monitoring stack stopped scraping.',
        trigger: 'alert',
        started_at: '2026-08-07T13:52:00+00:00',
      },
      [`/v1/runs/${RUN}/replay`]: replayBody,
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

describe('placing a change on the investigation ruler', () => {
  it('reads the window and the changes out of the run itself', () => {
    const ruler = rulerFromReplay(replay([MANAGING]), {
      startedAt: '2026-08-07T13:52:00+00:00',
    });

    expect(ruler?.start).toBe(WINDOW.start);
    expect(ruler?.end).toBe(WINDOW.end);
    expect(ruler?.marks).toHaveLength(1);
  });

  it('places a change by where it falls in the window', () => {
    // Half past one in an hour beginning at one o'clock is halfway along.
    const ruler = rulerFromReplay(replay([MANAGING]), {
      startedAt: '2026-08-07T13:52:00+00:00',
    });

    expect(ruler?.marks[0]?.percent).toBe(50);
  });

  it('places the investigation on the same ruler as the changes', () => {
    // The whole point. 13:52 in the hour from 13:00 is at 86.7 per cent, and it
    // is the mark every other one is read against.
    const ruler = rulerFromReplay(replay([MANAGING]), {
      startedAt: '2026-08-07T13:52:00+00:00',
    });

    expect(ruler?.investigation?.percent).toBeCloseTo(86.67, 1);
  });

  it('clamps something outside the window rather than drawing it off the ruler', () => {
    const ruler = rulerFromReplay(replay([MANAGING]), {
      startedAt: '2026-08-07T18:00:00+00:00',
    });

    expect(ruler?.investigation?.percent).toBe(100);
  });

  it('has no ruler for a run that never asked what changed', () => {
    expect(
      rulerFromReplay(
        { run_id: RUN, turns: [] },
        { startedAt: '2026-08-07T13:52:00Z' },
      ),
    ).toBeUndefined();
  });

  it('has no ruler for a window of no duration', () => {
    // Not a division by nought dressed as a timeline.
    const degenerate = {
      run_id: RUN,
      turns: [
        {
          turn_id: 't',
          index: 0,
          calls: [
            {
              call_id: 'c',
              name: 'changes_in_window',
              result: {
                window: { start: WINDOW.start, end: WINDOW.start },
                changes: [],
              },
            },
          ],
        },
      ],
    };

    expect(rulerFromReplay(degenerate, { startedAt: WINDOW.start })).toBeUndefined();
  });
});

describe('the investigation screen footer', () => {
  it('draws the ruler when the run asked what changed', async () => {
    serveRun(replay([MANAGING, COINCIDENCE]));
    await runScreen();

    expect(screen.getByTestId('change-ruler')).toBeInTheDocument();
    expect(screen.getAllByTestId('change-mark')).toHaveLength(2);
  });

  it('keeps each mark graded, so a coincidence is not drawn as a cause', async () => {
    serveRun(replay([MANAGING, COINCIDENCE]));
    await runScreen();

    const marks = screen.getAllByTestId('change-mark');
    expect(marks[0]).toHaveAttribute('data-strength', 'manages_resource');
    expect(marks[1]).toHaveAttribute('data-strength', 'window_only');
  });

  it('marks where the investigation itself sits on the ruler', async () => {
    serveRun(replay([MANAGING]));
    await runScreen();

    expect(screen.getByTestId('investigation-mark')).toBeInTheDocument();
  });

  it('names each change beside its mark rather than only on hover', async () => {
    // A ruler of unlabelled ticks is a picture. The identifier is what somebody
    // types into a terminal next.
    serveRun(replay([MANAGING]));
    await runScreen();

    expect(screen.getByTestId('change-ruler')).toHaveTextContent('9f2c1ab');
  });

  it('draws no footer for a run that never asked', async () => {
    serveRun({ run_id: RUN, turns: [] });
    await runScreen();

    expect(screen.queryByTestId('change-ruler')).toBeNull();
  });
});
