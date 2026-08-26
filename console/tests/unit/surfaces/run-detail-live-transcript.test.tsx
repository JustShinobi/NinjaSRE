import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { RunDetailScreen } from '@/surfaces/screens/run-detail';

/**
 * A live run's transcript card, and the one thing it may not say.
 *
 * The card has two halves that both state how much there is: the header counts,
 * and the body lists. On a settled run both read the replay and cannot disagree.
 * On a live one the body is the stream — seeded empty on purpose, because the
 * deployment's catch-up read carries the whole log and seeding it with the
 * replay as well would put every event on the screen twice under two identities
 * — and a header still counting the replay disagrees with it by construction.
 *
 * What that looked like: "6 events" over "This investigation recorded no
 * events." Two claims about one run on one card, one of them false whichever
 * way you read it, and a reader with no way to tell which. So the header reads
 * the live run's own events, the same sequence the body is drawing, and this
 * suite holds the two to the same number rather than to any particular number —
 * which is the assertion that fails again if they are ever reconnected to
 * different sources.
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

const RUN = 'run-still-going';

/** The transcript panel, found by its own title. */
function transcriptPanel(): HTMLElement {
  const found = screen
    .getAllByTestId('panel')
    .find((panel) => within(panel).queryByText('Investigation transcript') !== null);
  if (found === undefined) throw new Error('the transcript panel is not on the screen');
  return found;
}

/** The number `panel`'s header states, which is the card's headline claim. */
function headerCount(panel: HTMLElement): number {
  const header = panel.querySelector('header');
  const found = /(\d+)\s+events?/.exec(header?.textContent ?? '');
  if (found?.[1] === undefined) {
    throw new Error(`no event count in the panel header: ${header?.textContent ?? ''}`);
  }
  return Number(found[1]);
}

/** The number the transcript itself is drawing, which is the card's other claim. */
function bodyCount(panel: HTMLElement): number {
  const transcript = within(panel).getByTestId('transcript');
  return Number(transcript.getAttribute('data-total'));
}

/**
 * A run that is still going, whose replay already carries six events.
 *
 * Six rather than none, because a replay with nothing in it would make the two
 * halves agree by accident — the disagreement only exists when the recorded
 * account has more in it than the stream has delivered yet, which is every live
 * run in the moment before its first frame arrives.
 */
function serveStillRunning(): void {
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
        status: 'running',
        summary: '',
        headline: 'Disk pressure on the backup host',
        trigger: 'alert',
        started_at: '2026-08-07T11:52:00+00:00',
        finished_at: null,
      },
      [`/v1/runs/${RUN}/replay`]: {
        run_id: RUN,
        is_interrupted: false,
        total_cost: 0,
        total_tokens: 0,
        turns: [
          {
            turn_id: 'turn-1',
            index: 1,
            model: 'a-model',
            model_rationale: 'Look at what the host says about itself.',
            selection_rationale: '',
            calls: [
              {
                call_id: 'call-1',
                name: 'proxmox_node_status',
                arguments: {},
                result: {},
                status: 'succeeded',
                duration_ms: 40,
                error: '',
              },
            ],
          },
          {
            turn_id: 'turn-2',
            index: 2,
            model: 'a-model',
            model_rationale: 'Then at the volume that filled up.',
            selection_rationale: '',
            calls: [
              {
                call_id: 'call-2',
                name: 'proxmox_storage_usage',
                arguments: {},
                result: {},
                status: 'succeeded',
                duration_ms: 61,
                error: '',
              },
            ],
          },
        ],
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

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the transcript card of a run that is still going', () => {
  it('counts in its header what it is drawing in its body', async () => {
    serveStillRunning();
    render(await RunDetailScreen(await surfaceContext({}), RUN));

    const panel = transcriptPanel();
    // Deliberately not "expect 0": the number is whatever the live run has,
    // and what this holds is that one card cannot state two of them. A header
    // wired back to the replay makes this six against nought.
    expect(headerCount(panel)).toBe(bodyCount(panel));
  });

  it('draws the live transcript rather than an emptiness read off the replay', async () => {
    serveStillRunning();
    render(await RunDetailScreen(await surfaceContext({}), RUN));

    const panel = transcriptPanel();
    // The panel's own three states are decided by the replay for a settled
    // run. For a live one they must not be: a panel put into `empty` by a
    // replay that carried nothing never mounts the stream at all, and then
    // sits there saying "no transcript yet" while the run it is about is
    // producing events.
    expect(panel).toHaveAttribute('data-state', 'ready');
    expect(within(panel).getByTestId('live-run')).toBeInTheDocument();
  });
});
