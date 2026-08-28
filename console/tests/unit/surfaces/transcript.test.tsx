import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import {
  TRANSCRIPT_KINDS,
  eventsFromReplay,
  eventsFromStream,
  kindOf,
  usageFrom,
  type TranscriptEvent,
  type TranscriptKind,
} from '@/surfaces/transcript';
import { Transcript, TRANSCRIPT_WINDOW } from '@/surfaces/transcript-view';

import { rawMarkdown } from '../../e2e/bans';

/**
 * The transcript: one component, every event kind, and a cost that does not grow
 * with the length of the run.
 *
 * The budget below is read from `config/constants/console.py` rather than
 * restated, and it is asserted alongside the scaling claim rather than instead
 * of it. A wall-clock number on a loaded runner is a flake; the claim that the
 * number of entries in the document does not depend on how many there are is
 * both stronger and deterministic.
 */

function budget(name: string): number {
  const source = readFileSync(
    join(process.cwd(), '..', 'config', 'constants', 'console.py'),
    'utf8',
  );
  const found = new RegExp(`^${name}: Final = ([0-9.]+)`, 'm').exec(source);
  if (found?.[1] === undefined) {
    throw new Error(`${name} is not declared in config/constants/console.py`);
  }
  return Number(found[1]);
}

const TRANSCRIPT_BUDGET_MS = budget('CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS');

const KIND_LABELS = Object.fromEntries(
  TRANSCRIPT_KINDS.map((kind) => [kind, kind]),
) as Record<TranscriptKind, string>;

const LABELS = {
  kinds: KIND_LABELS,
  position: 'Showing the last 100 events.',
  earlier: 'Earlier events',
  later: 'Later events',
  empty: 'This run recorded no events.',
  arguments: 'Arguments',
  result: 'Result',
  note: 'Why these capabilities were offered',

  payload: {
    bounded: 'bounded',
    expand: 'Show the full payload',
    collapse: 'Bound it again',
    copy: 'Copy the raw payload',
    copied: 'Copied',
  },
  view: {
    narrated: 'Narrated',
    raw: 'Raw',
    payload: 'Raw payload',
  },
} as const;

function events(count: number): readonly TranscriptEvent[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `event-${String(index)}`,
    kind: TRANSCRIPT_KINDS[index % TRANSCRIPT_KINDS.length] ?? 'reasoning',
    rawKind: 'tool_called',
    at: '2026-08-07T11:56:00+00:00',
    title: 'estate.storage_pressure',
    detail: 'The datastore reading disagrees with the volume reading.',
    note: '',
    payload: '{"storage":"local-lvm"}',
    status: 'succeeded',
    durationMs: 412,
  }));
}

function renderTranscript(count: number): ReturnType<typeof render> {
  return render(<Transcript events={events(count)} labels={LABELS} times={{}} narrations={{}} />);
}

describe('a ten-thousand-event transcript', () => {
  it('draws the same number of entries as a hundred-event one', () => {
    const hundred = render(
      <Transcript events={events(TRANSCRIPT_WINDOW)} labels={LABELS} times={{}} narrations={{}} />,
    );
    const drawn = screen.getAllByTestId('transcript-event').length;
    hundred.unmount();

    renderTranscript(10_000);

    // The scaling assertion. This is the claim; the stopwatch below is the
    // sanity check on it.
    expect(screen.getAllByTestId('transcript-event')).toHaveLength(drawn);
    expect(drawn).toBe(TRANSCRIPT_WINDOW);
  });

  it('renders inside the declared budget', () => {
    const prepared = events(10_000);

    const started = performance.now();
    render(<Transcript events={prepared} labels={LABELS} times={{}} narrations={{}} />);
    const spent = performance.now() - started;

    expect(
      spent,
      `a ten-thousand-event transcript took ${spent.toFixed(0)}ms`,
    ).toBeLessThan(TRANSCRIPT_BUDGET_MS);
  });

  it('says how many there are rather than showing a hundred and stopping', () => {
    renderTranscript(10_000);

    expect(screen.getByTestId('transcript')).toHaveAttribute('data-total', '10000');
    expect(screen.getByTestId('transcript-position')).toHaveTextContent(
      LABELS.position,
    );
  });

  it('opens on the most recent events, which is what a person came for', () => {
    renderTranscript(10_000);

    expect(screen.getByTestId('later')).toBeDisabled();
    expect(screen.getByTestId('earlier')).toBeEnabled();
  });

  it('reaches the earlier ones without loading them all', async () => {
    renderTranscript(10_000);

    await userEvent.click(screen.getByTestId('earlier'));

    expect(screen.getAllByTestId('transcript-event')).toHaveLength(TRANSCRIPT_WINDOW);
    expect(screen.getByTestId('later')).toBeEnabled();
  });
});

describe('every kind of event', () => {
  it('is drawn, and is distinguishable from every other', () => {
    render(
      <Transcript
        events={TRANSCRIPT_KINDS.map((kind, index) => ({
          id: `event-${String(index)}`,
          kind,
          rawKind: kind,
          at: '',
          title: kind,
          note: '',
          detail: `what ${kind} means`,
          payload: '',
          status: '',
          durationMs: 0,
        }))}
        labels={LABELS}
        times={{}}
        narrations={{}}
      />,
    );

    const drawn = screen.getAllByTestId('transcript-event');
    expect(drawn).toHaveLength(TRANSCRIPT_KINDS.length);
    // Newest first: `Transcript` draws the array it is given in reverse
    // (`RunView.dc.html`'s "o mais novo primeiro"), so the events built here
    // in `TRANSCRIPT_KINDS` order are rendered in the opposite one — the
    // last one built is the "newest" and lands on top.
    expect(drawn.map((entry) => entry.getAttribute('data-kind'))).toEqual(
      [...TRANSCRIPT_KINDS].reverse(),
    );

    // Semantically distinct, not only visually: each entry says what kind it is
    // in words, and the roles separate the ones that matter most.
    const roles = new Set(drawn.map((entry) => entry.getAttribute('data-role')));
    expect(roles.size).toBeGreaterThan(1);
    const guardrail = drawn.find(
      (entry) => entry.getAttribute('data-kind') === 'guardrail',
    );
    expect(guardrail?.getAttribute('data-role')).toBe('danger');
  });

  it('says nothing when a run recorded nothing, rather than drawing a blank', () => {
    render(<Transcript events={[]} labels={LABELS} times={{}} narrations={{}} />);

    expect(screen.getByTestId('transcript')).toHaveTextContent(LABELS.empty);
  });
});

describe('a reasoning entry that is the model’s final answer', () => {
  // On the turn where the model stops calling capabilities, the rationale the
  // loop records for that turn is not a short aside — it is the model's whole
  // answer, in the same markdown the report document is written in
  // (`core/agent/react_loop.py` records `rationale=result.text`, and
  // `selection_rationale` is that same field replayed). A staging run proved
  // this reaches the screen raw: `### Investigation Summa"` printed as text
  // in the transcript, on a run whose report panel renders the identical
  // document correctly.
  it('draws a heading and emphasis instead of printing the marks themselves', () => {
    const rationale = '### Investigation Summary\n\nThe **primary** node lost quorum.';
    render(
      <Transcript
        events={[
          {
            id: 'turn-1-reasoning',
            kind: 'reasoning',
            rawKind: 'turn',
            at: '',
            title: '1',
            note: '',
            detail: rationale,
            payload: '',
            status: '',
            durationMs: 0,
          },
        ]}
        labels={LABELS}
        times={{}}
        narrations={{}}
      />,
    );

    const entry = screen.getByTestId('transcript-event');
    expect(rawMarkdown(entry.textContent || '')).toBeNull();
    expect(
      within(entry).getByRole('heading', { level: 3, name: 'Investigation Summary' }),
    ).toBeInTheDocument();
    expect(within(entry).getByText('primary').tagName).toBe('STRONG');
  });
});

describe('the two shapes a run arrives in', () => {
  const replay = {
    run_id: 'run-0001',
    total_tokens: 7360,
    total_cost: 0.124,
    summary: 'A guest reached the ceiling of its own volume.',
    turns: [
      {
        turn_id: 'turn-1',
        // The loop counts its own iterations from one, and the store
        // records what the loop counted. A fixture starting at zero was the
        // reason the console added one and showed every run counting from two.
        index: 1,
        model: 'operator-configured',
        selection_rationale: 'storage pressure is a first-party domain',
        calls: [
          {
            call_id: 'call-1',
            name: 'estate.storage_pressure',
            status: 'succeeded',
            duration_ms: 412,
            error: null,
          },
        ],
      },
    ],
  };

  const stream = {
    run_id: 'run-0003',
    events: [
      {
        run_id: 'run-0003',
        sequence: 0,
        kind: 'run_started',
        occurred_at: '2026-08-07T11:56:00+00:00',
        payload: { objective: 'A hardening unit failed at boot.' },
      },
      {
        run_id: 'run-0003',
        sequence: 2,
        kind: 'tool_called',
        occurred_at: '2026-08-07T11:56:01+00:00',
        payload: { name: 'estate.failed_units', arguments: { node: 'node01' } },
      },
    ],
  };

  it('reads a turn’s reasoning from the model, not from the selection note', () => {
    // Two different facts, and only one of them is the agent thinking. The
    // deployment's note about which capabilities were on offer is deterministic
    // prose it generated itself; putting it under the heading "Reasoning" is the
    // console reporting the deployment's own words back as the agent's.
    const built = eventsFromReplay({
      run_id: 'run-0002',
      turns: [
        {
          turn_id: 'turn-1',
          index: 1,
          model: 'gemini-flash-latest',
          model_rationale: 'The watchdog is stale for two jobs; I will read the tasks.',
          selection_rationale: 'ranked 60, offered 40, cut by the ceiling 20',
          calls: [],
        },
      ],
    });

    expect(built[0]?.detail).toBe(
      'The watchdog is stale for two jobs; I will read the tasks.',
    );
    expect(built[0]?.note).toBe('ranked 60, offered 40, cut by the ceiling 20');
  });

  it('numbers a turn the way the run recorded it', () => {
    // The store writes turn 1 as index 1. Adding one here made every screen
    // count from two, so an investigation with five turns showed turns 2 to 6
    // and no turn 1 anywhere.
    const built = eventsFromReplay({
      run_id: 'run-0002',
      turns: [{ turn_id: 'turn-1', index: 1, calls: [] }],
    });

    expect(built[0]?.title).toBe('1');
  });

  it('turns a recorded run into a turn’s reasoning, its call and its result', () => {
    const built = eventsFromReplay(replay);

    expect(built.map((each) => each.kind)).toEqual([
      'reasoning',
      'call',
      'result',
      'report',
    ]);
    expect(built[2]).toMatchObject({ status: 'succeeded', durationMs: 412 });
  });

  it('turns a live run into the same vocabulary', () => {
    const built = eventsFromStream(stream);

    expect(built.map((each) => each.kind)).toEqual(['objective', 'call']);
    expect(built[0]?.detail).toBe('A hardening unit failed at boot.');
  });

  it('carries an event kind it has never met rather than dropping it', () => {
    expect(kindOf('quantum_entangled')).toBe('reasoning');

    const built = eventsFromStream({
      events: [{ run_id: 'r', sequence: 1, kind: 'quantum_entangled', payload: {} }],
    });
    expect(built).toHaveLength(1);
    expect(built[0]?.rawKind).toBe('quantum_entangled');
  });

  it('breaks a run’s cost down by model and by turn', () => {
    const usage = usageFrom(replay);

    expect(usage.tokens).toBe(7360);
    expect(usage.byModel).toEqual([
      { model: 'operator-configured', turns: 1, tokens: 7360, cost: 0.124 },
    ]);
    expect(usage.byTurn[0]).toMatchObject({ turn: 1, calls: 1 });
  });

  it('reports nothing rather than dividing by nought for a run with no turns', () => {
    expect(usageFrom({ total_tokens: 0, total_cost: 0, turns: [] })).toEqual({
      tokens: 0,
      cost: 0,
      unpricedTurns: 0,
      // A run with no turns is not a priced run. There is nothing to price.
      priced: false,
      byModel: [],
      byTurn: [],
    });
  });
});

describe('what a run cost', () => {
  it('says how many turns carried no price, instead of calling them free', () => {
    // The gateway publishes `unpriced_turns` precisely so a screen can tell
    // "this cost nothing" from "nobody published a price for this model".
    // Reading only the total prints $0.00 over 36,842 tokens, which is the one
    // reading that is certainly wrong.
    const usage = usageFrom({
      turns: [
        { turn_id: 't1', index: 1, model: 'gemini-flash-latest', calls: [] },
        { turn_id: 't2', index: 2, model: 'gemini-flash-latest', calls: [] },
      ],
      total_tokens: 36842,
      total_cost: 0,
      unpriced_turns: 2,
    });

    expect(usage.unpricedTurns).toBe(2);
    expect(usage.priced).toBe(false);
  });

  it('numbers turns in the cost table the way the run recorded them', () => {
    const usage = usageFrom({
      turns: [{ turn_id: 't1', index: 1, model: 'm', calls: [] }],
      total_tokens: 10,
      total_cost: 1,
      unpriced_turns: 0,
    });

    expect(usage.byTurn[0]?.turn).toBe(1);
    expect(usage.priced).toBe(true);
  });
});

describe('an entry that arrives after the transcript already rendered', () => {
  // The board draws the newest event on top and annotates it with its own
  // arrival motion (`RunView.dc.html`'s `.newRow`) — proved here rather than
  // in the acceptance suite, which found no instant it could reliably poll
  // for between "the catch-up read landed" and "one more event arrived": the
  // local mock plane serves a live run's whole backlog in one response, so a
  // browser test racing a poll against it either caught the burst already
  // finished or asserted nothing meaningful. A synchronous re-render with
  // one appended event is exactly the instant this needs, and this is the
  // one place that can hold it still.
  it('marks only the newly appended event as just arrived, never the ones already drawn', async () => {
    const initial = events(3);
    const { rerender } = render(
      <Transcript events={initial} labels={LABELS} times={{}} narrations={{}} />,
    );
    await waitFor(() => {
      expect(screen.getAllByTestId('transcript-event')).toHaveLength(3);
    });
    // The catch-up read itself is never an arrival to animate — nothing is
    // marked once the first render (and the effect it triggers) has settled.
    expect(document.querySelectorAll('[data-just-arrived="true"]')).toHaveLength(0);

    const appended: TranscriptEvent = {
      id: 'event-new',
      kind: 'evidence',
      rawKind: 'observation_recorded',
      at: '2026-08-07T11:56:00+00:00',
      title: '',
      detail: 'a genuinely new observation',
      note: '',
      payload: '',
      status: '',
      durationMs: 0,
    };
    rerender(
      <Transcript events={[...initial, appended]} labels={LABELS} times={{}} narrations={{}} />,
    );

    await waitFor(() => {
      const marked = document.querySelectorAll('[data-just-arrived="true"]');
      expect(marked).toHaveLength(1);
    });
    const marked = document.querySelector('[data-just-arrived="true"]');
    expect(marked?.getAttribute('data-raw-kind')).toBe('observation_recorded');

    // Nothing already on screen before the append picked up the marker —
    // the newest one alone did.
    const stillUnmarked = screen
      .getAllByTestId('transcript-event')
      .filter((entry) => entry.getAttribute('data-raw-kind') !== 'observation_recorded');
    expect(stillUnmarked).toHaveLength(3);
    for (const entry of stillUnmarked) {
      expect(entry.getAttribute('data-just-arrived')).toBe('false');
    }
  });

  it('settles a settled run\'s own transcript without marking anything, ever', () => {
    // A replayed run's `events` never changes after mount — the effect
    // fires exactly once, sees the whole transcript already there, and
    // exempts it the same way the live run's own catch-up burst is exempt.
    render(<Transcript events={events(5)} labels={LABELS} times={{}} narrations={{}} />);
    expect(document.querySelectorAll('[data-just-arrived="true"]')).toHaveLength(0);
  });
});

describe('the single-transcript rule', () => {
  function sources(root: string): readonly string[] {
    const found: string[] = [];
    for (const entry of readdirSync(root)) {
      const path = join(root, entry);
      if (statSync(path).isDirectory()) {
        found.push(...sources(path));
      } else if (path.endsWith('.tsx') || path.endsWith('.ts')) {
        found.push(path);
      }
    }
    return found;
  }

  /** Every file under `src/` that contains `marker`, named relative to `src/`. */
  function carrying(marker: string): readonly string[] {
    return sources(join(process.cwd(), 'src'))
      .filter((path) => readFileSync(path, 'utf8').includes(marker))
      .map((path) => path.split('src'.concat('/'))[1] ?? path);
  }

  it('has exactly one component that draws a transcript entry', () => {
    // A second transcript would have to draw entries of its own, and every
    // entry this console draws carries this marker.
    expect(carrying(`data-testid="transcript-event"`)).toEqual([
      'surfaces/transcript-view.tsx',
    ]);
  });

  it('has exactly one place that decides how an event kind is presented', () => {
    // The other half of the same rule. A live view that agreed about the entry
    // markup and disagreed about which kinds are drawn at danger weight would be
    // two transcripts wearing one name.
    expect(carrying('KIND_ROLE[')).toEqual(['surfaces/transcript-view.tsx']);
  });
});
