import { describe, expect, it } from 'vitest';

import { cursorOf, NOTHING_SEEN, positionIn } from '@/live/cursor';
import { eventFrom, type StreamEvent } from '@/live/events';
import {
  applyEvent,
  applyEvents,
  CLOSING_KIND,
  decisionFor,
  isTerminal,
  openRun,
  OPENING_KIND,
  waitingFor,
} from '@/live/reducer';

/**
 * Exactly once, in order, across a reconnection — proved without a browser.
 *
 * This is the property the whole feature rests on and the one most likely to
 * regress, so it is asserted against a source that behaves the way a real one
 * does on a bad afternoon: it raises mid-flight, it replays what it already
 * sent, and it delivers a burst out of order. None of that needs a DOM, a timer
 * or a network, which is why the reducer is a pure function of (state, event)
 * and lives outside React.
 */

/** One event, spelled the way the gateway spells it on the wire. */
function frame(sequence: number, kind = 'observation_recorded'): unknown {
  return {
    run_id: 'run-0003',
    kind,
    sequence,
    occurred_at: '2026-08-07T11:57:00+00:00',
    turn_id: 'turn-0003-1',
    payload: { detail: `event ${String(sequence)}` },
  };
}

/** The event a wire document describes, or a failure naming the document. */
function must(document: unknown): StreamEvent {
  const event = eventFrom(document);
  if (event === null)
    throw new Error(`not a stream event: ${JSON.stringify(document)}`);
  return event;
}

function parsed(sequence: number, kind?: string): StreamEvent {
  return must(frame(sequence, kind));
}

/**
 * A stream that raises where it was told to and replays from a cursor after it.
 *
 * Deliberately adversarial in the three ways a real one is: the reconnection is
 * served everything from the cursor *inclusive*, so the client sees the last
 * event it already applied a second time; the tail is shuffled; and the source
 * has no idea what the client has.
 */
class AdversarialSource {
  readonly #total: number;
  readonly #breakAt: number;
  #raised = false;

  constructor(total: number, breakAt: number) {
    this.#total = total;
    this.#breakAt = breakAt;
  }

  /** Everything from `after` onwards, or as far as the break. */
  open(after: number): readonly StreamEvent[] {
    const from = after + 1;
    if (!this.#raised) {
      this.#raised = true;
      // The connection dies mid-flight: the client keeps what arrived and the
      // rest never does.
      return this.#range(from, this.#breakAt);
    }
    // On reconnect the server is generous and replays one it already sent,
    // out of order, which is the case duplicates have to be harmless in.
    const replayed = this.#range(Math.max(0, from - 1), this.#total);
    return [...replayed].reverse();
  }

  #range(from: number, until: number): readonly StreamEvent[] {
    const events: StreamEvent[] = [];
    for (let sequence = from; sequence < until; sequence += 1) {
      events.push(parsed(sequence));
    }
    return events;
  }
}

describe('the cursor', () => {
  it('is the run and the position together, because a position alone is ambiguous', () => {
    expect(cursorOf('run-0003', 7)).toBe('run-0003:7');
    expect(positionIn('run-0003:7', 'run-0003')).toBe(7);
  });

  it('is empty for a client that has seen nothing, so a first connect asks for everything', () => {
    expect(cursorOf('run-0003', NOTHING_SEEN)).toBe('');
    expect(positionIn('', 'run-0003')).toBe(NOTHING_SEEN);
  });

  it('refuses a cursor naming another run rather than reading somebody else’s backlog', () => {
    expect(positionIn('run-0009:7', 'run-0003')).toBe(NOTHING_SEEN);
    expect(positionIn('nonsense', 'run-0003')).toBe(NOTHING_SEEN);
  });
});

describe('the live reducer', () => {
  it('delivers every sequence exactly once, in order, across a connection error mid-flight', () => {
    const source = new AdversarialSource(40, 17);
    let state = openRun('run-0003');

    // The first connection dies at seventeen.
    state = applyEvents(state, source.open(state.position));
    expect(state.events).toHaveLength(17);
    expect(state.position).toBe(16);

    // The reconnection presents the cursor of the last event actually applied.
    expect(state.cursor).toBe('run-0003:16');
    state = applyEvents(state, source.open(positionIn(state.cursor, 'run-0003')));

    const sequences = state.events.map((event) => event.sequence);
    expect(sequences).toEqual([...Array(40).keys()]);
    expect(new Set(sequences).size).toBe(40);
    expect(state.position).toBe(39);
  });

  it('discards an event it has already applied rather than showing it twice', () => {
    let state = applyEvents(openRun('run-0003'), [parsed(0), parsed(1), parsed(2)]);
    const before = state.events;

    state = applyEvents(state, [parsed(0), parsed(1), parsed(2)]);

    expect(state.events).toEqual(before);
    expect(state.position).toBe(2);
    // Idempotent per sequence: applying the same event twice is applying it once.
    expect(applyEvent(state, parsed(2))).toEqual(state);
  });

  it('orders an out-of-order burst before exposing any of it', () => {
    const shuffled = [parsed(3), parsed(0), parsed(4), parsed(2), parsed(1)];

    const state = applyEvents(openRun('run-0003'), shuffled);

    expect(state.events.map((event) => event.sequence)).toEqual([0, 1, 2, 3, 4]);
  });

  it('holds an event that arrives before its predecessor instead of rendering a gap', () => {
    let state = applyEvents(openRun('run-0003'), [parsed(0), parsed(4)]);

    // Four is not on screen: a transcript with a hole in it is a transcript
    // somebody reads the wrong conclusion out of.
    expect(state.events.map((event) => event.sequence)).toEqual([0]);
    expect(state.held).toHaveLength(1);

    state = applyEvents(state, [parsed(1), parsed(2), parsed(3)]);
    expect(state.events.map((event) => event.sequence)).toEqual([0, 1, 2, 3, 4]);
    expect(state.held).toHaveLength(0);
  });

  it('ignores an event belonging to another run', () => {
    const other = must({ ...Object(frame(0)), run_id: 'run-0009' });

    const state = applyEvent(openRun('run-0003'), other);

    expect(state.events).toHaveLength(0);
    expect(state.position).toBe(NOTHING_SEEN);
  });

  it('carries the same vocabulary the replayed transcript uses', () => {
    const state = applyEvents(openRun('run-0003'), [parsed(0, 'guardrail_withheld')]);

    const [event] = state.events;
    expect(event?.kind).toBe('guardrail');
    expect(event?.rawKind).toBe('guardrail_withheld');
  });
});

describe('a run that ends while somebody is watching', () => {
  it('becomes the completed view without losing anything already on screen', () => {
    let state = applyEvents(openRun('run-0003'), [parsed(0), parsed(1)]);
    expect(isTerminal(state)).toBe(false);

    state = applyEvent(
      state,
      must({
        run_id: 'run-0003',
        kind: 'run_finished',
        sequence: 2,
        payload: { status: 'succeeded' },
      }),
    );

    expect(isTerminal(state)).toBe(true);
    expect(state.phase).toBe('completed');
    // Everything that was on screen is still on screen, and the terminal event
    // is on it too: becoming the completed view is a state change rather than a
    // reload, which is what keeps the scroll position.
    expect(state.events).toHaveLength(3);
  });

  it('tells a failure from a completion from a cancellation', () => {
    const phases = (kind: string, payload: unknown): string =>
      applyEvent(
        openRun('run-0003'),
        must({ run_id: 'run-0003', kind, sequence: 0, payload }),
      ).phase;

    expect(phases('run_finished', { status: 'failed' })).toBe('failed');
    expect(phases('run_finished', { status: 'cancelled' })).toBe('cancelled');
    expect(phases('run_interrupted', { reason: 'an operator took over' })).toBe(
      'cancelled',
    );
  });
});

describe('an interaction decided anywhere', () => {
  it('closes the card and names who decided it and where', () => {
    let state = applyEvent(
      openRun('run-0003'),
      must({
        run_id: 'run-0003',
        kind: OPENING_KIND,
        sequence: 0,
        payload: { interaction_id: 'int-0001', summary: 'Restart the hardening unit' },
      }),
    );
    expect(waitingFor(state, 'int-0001')).toBeDefined();

    state = applyEvent(
      state,
      must({
        run_id: 'run-0003',
        kind: CLOSING_KIND,
        sequence: 1,
        payload: {
          interaction_id: 'int-0001',
          waiting: false,
          decided_by: 'Avery Lockhart',
          decided_on: 'chat',
          verdict: 'approve',
        },
      }),
    );

    const decision = decisionFor(state, 'int-0001');
    expect(decision?.decidedBy).toBe('Avery Lockhart');
    expect(decision?.surface).toBe('chat');
    expect(decision?.verdict).toBe('approve');
    // Closed rather than removed: a card that vanished would leave the person
    // who was about to answer it wondering what they pressed.
    expect(waitingFor(state, 'int-0001')?.open).toBe(false);
  });

  it('does not close a card when the run merely starts waiting', () => {
    const state = applyEvent(
      openRun('run-0003'),
      must({
        run_id: 'run-0003',
        kind: CLOSING_KIND,
        sequence: 0,
        payload: { interaction_id: 'int-0001', waiting: true },
      }),
    );

    expect(decisionFor(state, 'int-0001')).toBeUndefined();
  });
});
