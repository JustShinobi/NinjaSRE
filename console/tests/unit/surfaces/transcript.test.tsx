import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { render, screen, within } from '@testing-library/react';
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

  payload: {
    bounded: 'bounded',
    expand: 'Show the full payload',
    collapse: 'Bound it again',
    copy: 'Copy the raw payload',
    copied: 'Copied',
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
    payload: '{"storage":"local-lvm"}',
    status: 'succeeded',
    durationMs: 412,
  }));
}

function renderTranscript(count: number): ReturnType<typeof render> {
  return render(<Transcript events={events(count)} labels={LABELS} times={{}} />);
}

describe('a ten-thousand-event transcript', () => {
  it('draws the same number of entries as a hundred-event one', () => {
    const hundred = render(
      <Transcript events={events(TRANSCRIPT_WINDOW)} labels={LABELS} times={{}} />,
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
    render(<Transcript events={prepared} labels={LABELS} times={{}} />);
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
          detail: `what ${kind} means`,
          payload: '',
          status: '',
          durationMs: 0,
        }))}
        labels={LABELS}
        times={{}}
      />,
    );

    const drawn = screen.getAllByTestId('transcript-event');
    expect(drawn).toHaveLength(TRANSCRIPT_KINDS.length);
    expect(drawn.map((entry) => entry.getAttribute('data-kind'))).toEqual([
      ...TRANSCRIPT_KINDS,
    ]);

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
    render(<Transcript events={[]} labels={LABELS} times={{}} />);

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
            detail: rationale,
            payload: '',
            status: '',
            durationMs: 0,
          },
        ]}
        labels={LABELS}
        times={{}}
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
        index: 0,
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
      byModel: [],
      byTurn: [],
    });
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
