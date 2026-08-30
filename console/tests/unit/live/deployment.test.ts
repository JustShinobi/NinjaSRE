import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DEPLOYMENT_REFRESH_BATCH_MS,
  DEPLOYMENT_STREAM_ADDRESS,
  DeploymentConnection,
  deploymentEventFromFrame,
  type DeploymentEvent,
} from '@/live/deployment';
import {
  BACKOFF_MS,
  MAX_RECONNECTIONS,
  type ConnectionState,
  type StreamHandlers,
  type StreamSource,
} from '@/live/connection';
import { sessionController } from '@/session/controller';

/**
 * The deployment channel's connection, held to the same three claims
 * `connection.test.ts` holds `RunConnection` to: it presents nothing false
 * about its own state, it gives up after a bounded number of attempts, and
 * closing it releases everything it held. Driven entirely through injected
 * time and an injected source, the same way.
 */

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

  /** Deliver one event, as the deployment channel spells it. */
  deliver(sequence: number, kind = 'run_started', scope = 'run'): void {
    this.handlers.onFrame(
      JSON.stringify({
        scope,
        kind,
        sequence,
        occurred_at: '2026-08-27T11:57:00+00:00',
        payload: { run_id: 'run-0003' },
      }),
    );
  }

  /** Deliver a resync control frame. */
  resync(): void {
    this.handlers.onFrame(
      JSON.stringify({ scope: 'control', kind: 'resync', sequence: 0, payload: {} }),
    );
  }
}

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

  advance(): void {
    const due = [...this.pending];
    this.pending.length = 0;
    for (const entry of due) entry.run();
  }
}

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
  readonly connection: DeploymentConnection;
  readonly source: FakeSource;
  readonly clock: FakeClock;
  readonly visibility: FakeVisibility;
  readonly states: ConnectionState[];
  readonly batches: DeploymentEvent[][];
  resyncs: number;
}

function harness(): Harness {
  const source = new FakeSource();
  const clock = new FakeClock();
  const visibility = new FakeVisibility();
  const states: ConnectionState[] = [];
  const batches: DeploymentEvent[][] = [];
  const held = { resyncs: 0 };

  const connection = new DeploymentConnection({
    source,
    scheduler: clock,
    visibility,
    onState: (state) => {
      states.push(state);
    },
    onEvents: (events) => {
      batches.push([...events]);
    },
    onResync: () => {
      held.resyncs += 1;
    },
  });

  return {
    connection,
    source,
    clock,
    visibility,
    states,
    batches,
    get resyncs(): number {
      return held.resyncs;
    },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('DeploymentConnection', () => {
  it('opens the deployment channel address, not a run-scoped one', () => {
    const { connection, source } = harness();
    connection.open();
    expect(source.addresses).toEqual([DEPLOYMENT_STREAM_ADDRESS]);
  });

  it('delivers a batch after the batch window, not per event', () => {
    const { connection, source, clock, batches } = harness();
    connection.open();
    source.handlers.onOpen();
    source.deliver(1);
    source.deliver(2);
    expect(batches).toEqual([]);

    clock.advance();
    expect(batches).toHaveLength(1);
    expect(batches[0]).toHaveLength(2);
    expect(batches[0]?.[0]?.sequence).toBe(1);
    expect(batches[0]?.[1]?.sequence).toBe(2);
  });

  it('waits exactly DEPLOYMENT_REFRESH_BATCH_MS before flushing', () => {
    const { connection, source, clock } = harness();
    connection.open();
    source.handlers.onOpen();
    source.deliver(1);
    expect(clock.pending.map((entry) => entry.after)).toEqual([
      DEPLOYMENT_REFRESH_BATCH_MS,
    ]);
  });

  it('a resync calls onResync immediately, never batched with events', () => {
    const held = harness();
    held.connection.open();
    held.source.handlers.onOpen();
    held.source.resync();
    expect(held.resyncs).toBe(1);
    expect(held.batches).toEqual([]);
  });

  it('a resync interleaved with real events does not delay them into one batch', () => {
    const { connection, source, clock, batches } = harness();
    connection.open();
    source.handlers.onOpen();
    source.deliver(1);
    source.resync();
    clock.advance();
    expect(batches).toHaveLength(1);
    expect(batches[0]).toHaveLength(1);
  });

  it('state moves connecting -> connected on the first open', () => {
    const { connection, source, states } = harness();
    connection.open();
    expect(states).toEqual(['connecting']);
    source.handlers.onOpen();
    expect(states).toEqual(['connecting', 'connected']);
  });

  it('backs off on failure using the same table RunConnection uses', () => {
    const { connection, source, clock, states } = harness();
    connection.open();
    source.handlers.onOpen();
    source.handlers.onError(0);
    expect(states).toEqual(['connecting', 'connected', 'reconnecting']);
    expect(clock.pending.map((entry) => entry.after)).toEqual([BACKOFF_MS[0]]);
  });

  it('gives up after MAX_RECONNECTIONS attempts', () => {
    const { connection, source, clock, states } = harness();
    connection.open();
    for (let attempt = 0; attempt < MAX_RECONNECTIONS; attempt += 1) {
      source.handlers.onError(0);
      clock.advance();
    }
    source.handlers.onError(0);
    expect(connection.exhausted).toBe(true);
    expect(states.at(-1)).toBe('disconnected');
  });

  it('a 401 ends the session instead of retrying', () => {
    const reported = vi
      .spyOn(sessionController, 'unauthorized')
      .mockImplementation(() => undefined);
    const { connection, source, states } = harness();
    connection.open();
    source.handlers.onError(401);
    expect(states.at(-1)).toBe('disconnected');
    expect(connection.exhausted).toBe(false);
    expect(reported).toHaveBeenCalledTimes(1);
  });

  it('pauses on a hidden tab and resumes on return, the same policy RunConnection uses', () => {
    const { connection, visibility, states } = harness();
    connection.open();
    visibility.set(true);
    expect(states.at(-1)).toBe('idle');
    visibility.set(false);
    // Resting state before hiding was 'connecting'; returning to it, not to 'idle'.
    expect(states.at(-1)).toBe('connecting');
  });

  it('close releases the stream, the retry, the flush and the visibility listener', () => {
    const { connection, source, clock, visibility } = harness();
    connection.open();
    source.handlers.onOpen();
    source.deliver(1);
    expect(visibility.listeners).toBe(1);

    connection.close();
    expect(source.closed).toEqual([DEPLOYMENT_STREAM_ADDRESS]);
    expect(visibility.listeners).toBe(0);
    expect(clock.pending).toEqual([]);
    expect(connection.state).toBe('disconnected');
  });
});

describe('deploymentEventFromFrame', () => {
  it('reads scope, kind, sequence, occurred_at and payload', () => {
    const event = deploymentEventFromFrame(
      JSON.stringify({
        scope: 'incident',
        kind: 'incident_opened',
        sequence: 4,
        occurred_at: '2026-08-27T12:00:00+00:00',
        payload: { incident_id: 'inc-1' },
      }),
    );
    expect(event).toEqual({
      scope: 'incident',
      kind: 'incident_opened',
      sequence: 4,
      occurredAt: '2026-08-27T12:00:00+00:00',
      payload: { incident_id: 'inc-1' },
    });
  });

  it('returns null for an empty frame', () => {
    expect(deploymentEventFromFrame('')).toBeNull();
  });

  it('returns null for a frame that is not JSON, rather than throwing', () => {
    expect(deploymentEventFromFrame('not json')).toBeNull();
  });

  it('returns null for a frame with no kind', () => {
    expect(deploymentEventFromFrame(JSON.stringify({ sequence: 1 }))).toBeNull();
  });
});
