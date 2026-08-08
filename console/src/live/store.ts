import {
  RunConnection,
  type ConnectionState,
  type Scheduler,
  type StreamSource,
  type Visibility,
} from './connection';
import type { StreamEvent } from './events';
import { applyEvents, openRun, type LiveState, type Seed } from './reducer';

/**
 * One subscription per run, shared by everything on the page.
 *
 * A run's screen is a transcript, a cost panel, an approval card and a
 * notification count — four consumers of one stream. Four subscriptions would
 * quadruple the deployment's fan-out, and worse, would let the four disagree
 * about what has arrived: the count would say two while the card it names had
 * already closed. So the connection is held here, reference-counted, and the
 * last screen to leave closes it.
 *
 * The store is the single place the reducer's output lives. Screens read it and
 * never keep their own copy, which is what makes "a count and a list cannot
 * disagree" a fact about the shape of the code rather than a thing to remember.
 */

/** One run, as everything watching it sees it. */
export interface RunSnapshot {
  readonly live: LiveState;
  readonly connection: ConnectionState;
  /** Whether the reconnection bound was reached, which is when a reload is offered. */
  readonly exhausted: boolean;
}

interface Entry {
  snapshot: RunSnapshot;
  connection: RunConnection;
  listeners: Set<() => void>;
}

export interface RunStoreOptions {
  readonly source: StreamSource;
  readonly scheduler?: Scheduler;
  readonly visibility?: Visibility;
}

export class RunStore {
  readonly #options: RunStoreOptions;
  readonly #runs = new Map<string, Entry>();
  /**
   * What a run looks like before anything is watching it.
   *
   * Cached rather than built per call, because React compares snapshots by
   * identity: a `getSnapshot` that returned a fresh object every time would
   * re-render for ever without a single event having arrived.
   */
  readonly #resting = new Map<string, RunSnapshot>();
  /** How many streams have ever been opened, which is what a fan-out test counts. */
  #opened = 0;

  constructor(options: RunStoreOptions) {
    this.#options = options;
  }

  get opened(): number {
    return this.#opened;
  }

  /**
   * Watch `runId`, seeded with what the server already rendered.
   *
   * The seed is used only when the stream is opened, not on every subscriber: a
   * second consumer arriving mid-run must join what is already there rather
   * than resetting it to what its own props happened to say.
   */
  subscribe(runId: string, seed: Seed, listener: () => void): () => void {
    const entry = this.#entry(runId, seed);
    entry.listeners.add(listener);
    return () => {
      entry.listeners.delete(listener);
      if (entry.listeners.size > 0) return;
      // The last screen watching this run has gone. Nothing keeps a connection
      // open for a page nobody is on.
      entry.connection.close();
      this.#runs.delete(runId);
    };
  }

  /** What `runId` looks like now. Stable between changes, so React can compare it. */
  snapshot(runId: string, seed: Seed = {}): RunSnapshot {
    const watched = this.#runs.get(runId);
    if (watched !== undefined) return watched.snapshot;
    const held = this.#resting.get(runId);
    if (held !== undefined) return held;
    const fresh = resting(runId, seed);
    this.#resting.set(runId, fresh);
    return fresh;
  }

  /**
   * Try again after the bound was reached.
   *
   * Offered rather than automatic: retries are exhausted precisely because
   * retrying was not working, and a console that quietly kept going would be
   * showing a stale transcript with a live badge on it.
   */
  reopen(runId: string): void {
    const entry = this.#runs.get(runId);
    if (entry === undefined) return;
    const seed: Seed = {
      events: entry.snapshot.live.events,
      position: entry.snapshot.live.position,
      phase: entry.snapshot.live.phase,
      waiting: entry.snapshot.live.waiting,
    };
    entry.connection.close();
    this.#runs.delete(runId);
    const fresh = this.#entry(runId, seed);
    for (const listener of entry.listeners) fresh.listeners.add(listener);
    this.#publish(runId);
  }

  #entry(runId: string, seed: Seed): Entry {
    const held = this.#runs.get(runId);
    if (held !== undefined) return held;
    this.#resting.delete(runId);

    const entry: Entry = {
      snapshot: resting(runId, seed),
      listeners: new Set(),
      connection: new RunConnection({
        runId,
        source: this.#options.source,
        ...(this.#options.scheduler === undefined
          ? {}
          : { scheduler: this.#options.scheduler }),
        ...(this.#options.visibility === undefined
          ? {}
          : { visibility: this.#options.visibility }),
        cursor: () => this.#runs.get(runId)?.snapshot.live.cursor ?? '',
        onState: (connection) => {
          this.#update(runId, (snapshot) => ({
            ...snapshot,
            connection,
            exhausted: entry.connection.exhausted,
          }));
        },
        onEvents: (events: readonly StreamEvent[]) => {
          this.#update(runId, (snapshot) => ({
            ...snapshot,
            live: applyEvents(snapshot.live, events),
          }));
        },
      }),
    };
    this.#runs.set(runId, entry);
    this.#opened += 1;
    entry.connection.open();
    return entry;
  }

  #update(runId: string, change: (snapshot: RunSnapshot) => RunSnapshot): void {
    const entry = this.#runs.get(runId);
    if (entry === undefined) return;
    const next = change(entry.snapshot);
    if (next === entry.snapshot) return;
    entry.snapshot = next;
    this.#publish(runId);
  }

  #publish(runId: string): void {
    const entry = this.#runs.get(runId);
    if (entry === undefined) return;
    for (const listener of [...entry.listeners]) listener();
  }
}

/** A run nobody is watching: whatever the server rendered, and no connection. */
function resting(runId: string, seed: Seed): RunSnapshot {
  return { live: openRun(runId, seed), connection: 'disconnected', exhausted: false };
}
