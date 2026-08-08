import { afterEach, describe, expect, it, vi } from 'vitest';

import { framesIn } from '@/live/sse';
import {
  BACKOFF_MS,
  MAX_RECONNECTIONS,
  RunConnection,
  streamAddress,
  type ConnectionState,
  type StreamHandlers,
  type StreamSource,
} from '@/live/connection';
import { sessionController } from '@/session/controller';

/**
 * The transport, held to the three claims a live view cannot be trusted without.
 *
 * It presents the cursor it actually reached. It gives up after a bounded number
 * of attempts and says so, rather than retrying for ever against a deployment
 * that has gone away — which looks identical to one that is working. And it is
 * torn down when the screen closes, because a subscription that outlives its
 * screen is a browser tab quietly holding a connection open on a gateway.
 *
 * Everything here is driven through injected time and an injected source, so
 * none of it is a wait and none of it can flake.
 */

/** A source that records what it was asked for and is driven by the test. */
class FakeSource implements StreamSource {
  readonly addresses: string[] = [];
  readonly closed: string[] = [];
  #handlers: StreamHandlers | null = null;

  open(address: string, handlers: StreamHandlers): { close: () => void } {
    this.addresses.push(address);
    this.#handlers = handlers;
    return {
      close: () => {
        this.closed.push(address);
      },
    };
  }

  get handlers(): StreamHandlers {
    if (this.#handlers === null) throw new Error('nothing has opened this source');
    return this.#handlers;
  }

  /** Deliver one event, as the gateway spells it. */
  deliver(sequence: number, runId = 'run-0003'): void {
    this.handlers.onFrame(
      JSON.stringify({
        run_id: runId,
        kind: 'observation_recorded',
        sequence,
        occurred_at: '2026-08-07T11:57:00+00:00',
        payload: { detail: 'something happened' },
      }),
    );
  }
}

/** Time, as a list of things that have not happened yet. */
class FakeClock {
  readonly pending: { readonly after: number; readonly run: () => void }[] = [];

  after(ms: number, run: () => void): () => void {
    const entry = { after: ms, run };
    this.pending.push(entry);
    return () => {
      const at = this.pending.indexOf(entry);
      if (at >= 0) this.pending.splice(at, 1);
    };
  }

  /** Run everything scheduled, in the order it was scheduled. */
  advance(): void {
    const due = [...this.pending];
    this.pending.length = 0;
    for (const entry of due) entry.run();
  }
}

/** A tab that can be sent to the background and brought back. */
class FakeVisibility {
  #hidden = false;
  #listeners: (() => void)[] = [];

  hidden(): boolean {
    return this.#hidden;
  }

  onChange(listener: () => void): () => void {
    this.#listeners.push(listener);
    return () => {
      this.#listeners = this.#listeners.filter((held) => held !== listener);
    };
  }

  set(hidden: boolean): void {
    this.#hidden = hidden;
    for (const listener of [...this.#listeners]) listener();
  }

  get listeners(): number {
    return this.#listeners.length;
  }
}

interface Harness {
  readonly connection: RunConnection;
  readonly source: FakeSource;
  readonly clock: FakeClock;
  readonly visibility: FakeVisibility;
  readonly states: ConnectionState[];
  readonly applied: number[];
  cursor: string;
}

function harness(): Harness {
  const source = new FakeSource();
  const clock = new FakeClock();
  const visibility = new FakeVisibility();
  const states: ConnectionState[] = [];
  const applied: number[] = [];
  const held = { cursor: '' };

  const connection = new RunConnection({
    runId: 'run-0003',
    source,
    scheduler: clock,
    visibility,
    cursor: () => held.cursor,
    onState: (state) => states.push(state),
    onEvents: (events) => {
      for (const event of events) {
        applied.push(event.sequence);
        held.cursor = `run-0003:${String(event.sequence)}`;
      }
    },
  });

  return {
    connection,
    source,
    clock,
    visibility,
    states,
    applied,
    get cursor() {
      return held.cursor;
    },
    set cursor(value: string) {
      held.cursor = value;
    },
  };
}

afterEach(() => {
  sessionController.reset();
});

describe('server-sent event framing', () => {
  it('reads a frame’s id and data, and carries an incomplete one over', () => {
    const first = framesIn('id: run-0003:1\nevent: x\ndata: {"a":1}\n\ndata: {"b"');

    expect(first.frames).toHaveLength(1);
    expect(first.frames[0]?.id).toBe('run-0003:1');
    expect(first.frames[0]?.data).toBe('{"a":1}');
    // The tail is not a frame yet, and dropping it would lose an event on every
    // chunk boundary the network happens to put in the middle of one.
    expect(first.rest).toBe('data: {"b"');

    const second = framesIn(`${first.rest}:2}\n\n`);
    expect(second.frames[0]?.data).toBe('{"b":2}');
  });

  it('marks a keep-alive comment as one rather than as an empty event', () => {
    const { frames } = framesIn(': heartbeat\n\n');

    expect(frames[0]?.comment).toBe(true);
    expect(frames[0]?.data).toBe('');
  });
});

describe('a live run’s connection', () => {
  it('presents nothing on a first connection and the cursor on every one after', () => {
    const test = harness();
    test.connection.open();

    expect(test.source.addresses[0]).toBe(streamAddress('run-0003', ''));

    test.source.deliver(0);
    test.source.deliver(1);
    test.clock.advance();
    expect(test.applied).toEqual([0, 1]);

    test.source.handlers.onError(0);
    test.clock.advance();

    expect(test.source.addresses[1]).toBe(streamAddress('run-0003', 'run-0003:1'));
    expect(test.source.addresses[1]).toContain('cursor=run-0003%3A1');
  });

  it('says connected, reconnecting and disconnected where somebody can see it', () => {
    const test = harness();
    test.connection.open();
    expect(test.states).toContain('connecting');

    test.source.handlers.onOpen();
    expect(test.connection.state).toBe('connected');

    test.source.handlers.onError(0);
    expect(test.connection.state).toBe('reconnecting');
    expect(test.states).toContain('reconnecting');
  });

  it('backs off, bounded, and then says it has given up rather than retrying for ever', () => {
    const test = harness();
    test.connection.open();

    const waits: number[] = [];
    for (let attempt = 0; attempt <= MAX_RECONNECTIONS; attempt += 1) {
      test.source.handlers.onError(0);
      const [next] = test.clock.pending;
      if (next !== undefined) waits.push(next.after);
      test.clock.advance();
    }

    // Bounded above by the declared ceiling, and never longer than it.
    const ceiling = BACKOFF_MS[BACKOFF_MS.length - 1] ?? 0;
    expect(Math.max(...waits)).toBeLessThanOrEqual(ceiling);
    expect(waits[0]).toBeLessThan(ceiling);

    expect(test.connection.state).toBe('disconnected');
    expect(test.connection.exhausted).toBe(true);
    // Nothing is left scheduled: a disconnected connection is not a slow one.
    expect(test.clock.pending).toHaveLength(0);
    expect(test.source.addresses.length).toBeLessThanOrEqual(MAX_RECONNECTIONS + 1);
  });

  it('forgets its attempts once an event actually arrives', () => {
    const test = harness();
    test.connection.open();

    for (let attempt = 0; attempt < 3; attempt += 1) {
      test.source.handlers.onError(0);
      test.clock.advance();
    }
    expect(test.connection.attempts).toBe(3);

    test.source.deliver(0);
    test.clock.advance();

    expect(test.connection.attempts).toBe(0);
  });

  it('ends the session through the one collapse path when the stream is refused', () => {
    const test = harness();
    const endings: string[] = [];
    sessionController.listen((ending) => endings.push(ending.reason));
    test.connection.open();

    test.source.handlers.onError(401);

    expect(endings).toEqual(['expired']);
    expect(sessionController.hasEnded).toBe(true);
    // And it does not then sit there reconnecting into a session that is over.
    expect(test.clock.pending).toHaveLength(0);
    expect(test.connection.state).toBe('disconnected');
  });

  it('is torn down when the screen closes, leaving nothing behind', () => {
    const test = harness();
    test.connection.open();
    test.source.handlers.onOpen();

    test.connection.close();

    expect(test.source.closed).toHaveLength(1);
    expect(test.clock.pending).toHaveLength(0);
    expect(test.visibility.listeners).toBe(0);
    expect(test.connection.state).toBe('disconnected');
  });

  it('opens and closes the same number of times over a hundred mount cycles', () => {
    const source = new FakeSource();
    const clock = new FakeClock();
    const visibility = new FakeVisibility();

    for (let cycle = 0; cycle < 100; cycle += 1) {
      const connection = new RunConnection({
        runId: 'run-0003',
        source,
        scheduler: clock,
        visibility,
        cursor: () => '',
        onState: () => undefined,
        onEvents: () => undefined,
      });
      connection.open();
      connection.close();
    }

    expect(source.closed).toHaveLength(100);
    expect(source.addresses).toHaveLength(100);
    // Nothing accumulates: no timer, and no listener on a page-level event.
    expect(clock.pending).toHaveLength(0);
    expect(visibility.listeners).toBe(0);
  });

  it('does no work while the tab is in the background, and recovers fully on return', () => {
    const test = harness();
    test.connection.open();
    test.source.handlers.onOpen();

    test.visibility.set(true);
    test.source.deliver(0);
    test.source.deliver(1);
    test.clock.advance();

    // Nothing has been applied, because nothing is being drawn.
    expect(test.applied).toEqual([]);
    expect(test.connection.state).toBe('idle');

    test.visibility.set(false);
    test.clock.advance();

    // Everything that arrived while it was away is applied, once, in order.
    expect(test.applied).toEqual([0, 1]);
    expect(test.connection.state).not.toBe('idle');
  });

  it('does not reconnect while the tab is hidden, and reconnects when it comes back', () => {
    const test = harness();
    test.connection.open();
    test.visibility.set(true);

    test.source.handlers.onError(0);
    test.clock.advance();

    expect(test.source.addresses).toHaveLength(1);

    test.visibility.set(false);
    test.clock.advance();

    expect(test.source.addresses).toHaveLength(2);
  });

  it('applies a burst as one batch rather than once per event', () => {
    const test = harness();
    const batches: number[] = [];
    const connection = new RunConnection({
      runId: 'run-0003',
      source: test.source,
      scheduler: test.clock,
      visibility: test.visibility,
      cursor: () => '',
      onState: () => undefined,
      onEvents: (events) => batches.push(events.length),
    });
    connection.open();

    for (let sequence = 0; sequence < 500; sequence += 1) test.source.deliver(sequence);
    test.clock.advance();

    expect(batches).toEqual([500]);
    connection.close();
  });

  it('skips a keep-alive and a frame it cannot read without ending the stream', () => {
    const test = harness();
    test.connection.open();

    test.source.handlers.onFrame('');
    test.source.handlers.onFrame('not json');
    test.source.deliver(0);
    test.clock.advance();

    expect(test.applied).toEqual([0]);
    expect(test.connection.state).not.toBe('disconnected');
  });
});

describe('the address a stream is opened at', () => {
  it('goes through the console’s own origin, because the credential is a cookie', () => {
    expect(streamAddress('run-0003', '')).toBe('/api/stream/run-0003');
  });

  it('encodes a run identifier rather than pasting it into a path', () => {
    expect(streamAddress('run/0003', '')).toBe('/api/stream/run%2F0003');
  });
});

describe('the browser transport', () => {
  it('reports the status of a refusal rather than a generic failure', async () => {
    const { fetchStreamSource } = await import('@/live/transport');
    const statuses: number[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('', { status: 401 })),
    );

    const handle = fetchStreamSource.open('/api/stream/run-0003', {
      onOpen: () => undefined,
      onFrame: () => undefined,
      onError: (status) => statuses.push(status),
    });
    await vi.waitFor(() => {
      expect(statuses).toEqual([401]);
    });
    handle.close();
    vi.unstubAllGlobals();
  });
});
