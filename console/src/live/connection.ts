import { reportUnauthorized } from '@/session/controller';
import { eventFromFrame, type StreamEvent } from './events';

/**
 * One run's stream, with the four things that make it trustworthy.
 *
 * It presents the cursor it actually reached, so a reconnection resumes rather
 * than restarting or skipping. It backs off and gives up, because a console
 * that retries for ever against a deployment that has gone away looks exactly
 * like one that is working. It says which of those it is doing, where the
 * operator can see it. And it can be closed, completely, because a subscription
 * that outlives its screen is a tab quietly holding a connection open.
 *
 * Time, the transport and the tab's visibility are all injected. Nothing here
 * waits, so nothing here flakes, and the whole of it is provable in a unit test.
 *
 * The engine underneath (`ReconnectingChannel`, below) is shared with
 * `deployment.ts`'s `DeploymentConnection`: a run's stream and the
 * deployment-wide channel differ only in where they open, how they read one
 * frame, how long they may batch before handing a delivery over, and the two
 * things a run's stream has no need of — the deployment channel's `resync`,
 * and the notice a channel owes its reader when it *re*-opens (`onReconnect`;
 * a stream that presents a cursor resumes on its own and has no gap to
 * confess). Everything else — state, teardown, the backoff table, the
 * ten-attempt bound, pausing for a hidden tab and resuming into whatever it
 * was doing before — is written once, so a fix applied here is a fix applied
 * to both.
 */

/** What the connection is doing, in the words the indicator uses. */
export const CONNECTION_STATES = [
  'connecting',
  'connected',
  'reconnecting',
  /** Nothing is being drawn, because the tab is in the background. */
  'idle',
  'disconnected',
] as const;

export type ConnectionState = (typeof CONNECTION_STATES)[number];

/**
 * How long to wait before each reconnection, in milliseconds.
 *
 * Doubling, and bounded: the last value is the ceiling and every attempt past
 * the fifth waits exactly that. A backoff with no ceiling turns a deployment
 * that comes back after ten minutes into a console that notices half an hour
 * later.
 */
export const BACKOFF_MS: readonly number[] = [500, 1000, 2000, 4000, 8000];

/**
 * How many reconnections are attempted before the console says it has stopped.
 *
 * The same bound the deployment's own reader uses, held against it by
 * `tests/contract/console/test_console_live.py`.
 */
export const MAX_RECONNECTIONS = 10;

/** Where a run's stream is read from. */
export function streamAddress(runId: string, cursor: string): string {
  const path = `/api/stream/${encodeURIComponent(runId)}`;
  return cursor === '' ? path : `${path}?cursor=${encodeURIComponent(cursor)}`;
}

/** What a transport tells the connection about. */
export interface StreamHandlers {
  onOpen: () => void;
  /** One frame's data, already lifted out of the SSE framing. */
  onFrame: (data: string) => void;
  /** The stream ended. `status` is the refusal's, or nought when there was none. */
  onError: (status: number) => void;
}

/** Something that can be stopped. */
export interface StreamHandle {
  close: () => void;
}

/** Whatever actually opens a stream. Injected, so the suite drives a fake. */
export interface StreamSource {
  open: (address: string, handlers: StreamHandlers) => StreamHandle;
}

/** Time, as the ability to be told about later. */
export interface Scheduler {
  after: (ms: number, run: () => void) => () => void;
}

/** Whether this tab is being looked at. */
export interface Visibility {
  hidden: () => boolean;
  onChange: (listener: () => void) => () => void;
}

/** The browser's own timer, for a connection nobody injected one into. */
export const wallClock: Scheduler = {
  after: (ms, run) => {
    const handle = setTimeout(run, ms);
    return () => {
      clearTimeout(handle);
    };
  },
};

/** The browser's own visibility, likewise. */
export const documentVisibility: Visibility = {
  hidden: () =>
    typeof document !== 'undefined' && document.visibilityState === 'hidden',
  onChange: (listener) => {
    if (typeof document === 'undefined') return () => undefined;
    document.addEventListener('visibilitychange', listener);
    return () => {
      document.removeEventListener('visibilitychange', listener);
    };
  },
};

/**
 * What every reconnecting channel needs, parametrized over the handful of
 * things that actually differ between one and another.
 */
export interface ChannelOptions<E> {
  readonly source: StreamSource;
  /**
   * Where to open. Read fresh on every attempt — a run's stream presents
   * whatever cursor it last reached; the deployment channel's address never
   * changes.
   */
  readonly address: () => string;
  /** One frame's `data`, turned into an event, or `null` for a frame this channel has nothing to do with. */
  readonly decode: (data: string) => E | null;
  /**
   * How long a batch of decoded events is allowed to accumulate before
   * `onEvents` receives it, in ms. Nought — the next scheduler tick,
   * batching only what genuinely arrived in the same instant — unless told
   * otherwise.
   */
  readonly batchDelayMs?: number;
  /**
   * An event that must bypass the batch entirely and reach `onImmediate` at
   * once — the deployment channel's `resync`, a confession rather than a
   * fact to accumulate alongside whatever else arrived. A run's stream has
   * nothing like it and leaves both this and `onImmediate` unset.
   */
  readonly isImmediate?: (event: E) => boolean;
  readonly onImmediate?: (event: E) => void;
  readonly onState: (state: ConnectionState) => void;
  readonly onEvents: (events: readonly E[]) => void;
  /**
   * Called when a stream opens that is a *re*-open — the channel had dropped,
   * and whatever the deployment published between the drop and this moment
   * reached a connection that was no longer listening.
   *
   * It reports only that there was a gap, never what was in it, because this
   * channel has no way to know: it presents no cursor, and one that did would
   * still be bounded by however much the broker still holds in memory. Saying
   * *that* something was missed is the whole of what a reader needs when its
   * answer to everything is one re-read.
   *
   * A first connection never raises it. The page a channel opens from was
   * rendered by the server moments before, so its silence is not a gap, and a
   * re-read there would buy nothing and cost a round trip on every
   * navigation. Reaching `connected` is therefore not the signal — *reaching
   * it a second time* is.
   *
   * `RunConnection` leaves it unset, and that is an answer rather than an
   * omission: a run's stream presents the cursor it actually reached, so its
   * reconnection resumes at the event after the last one applied. There is no
   * gap for it to confess.
   */
  readonly onReconnect?: () => void;
  /**
   * Called on every failed attempt, with the running count — including a
   * second, third, ... consecutive failure that leaves the state as
   * `reconnecting` both before and after. `onState` is not that signal: it
   * fires on *change* (`#setState` below drops a call that would not change
   * the state string), so a caller that needs to know how many attempts have
   * failed — a chip deciding when a retry has gone on long enough to call it
   * `stale` rather than `refreshing`, say — needs this instead of trying to
   * infer it from `onState`.
   */
  readonly onAttempt?: (attempts: number) => void;
  readonly scheduler?: Scheduler;
  readonly visibility?: Visibility;
}

/**
 * The backoff, the batching, the visibility pause and the bounded-retry
 * give-up — written once, and composed by both `RunConnection` and
 * `DeploymentConnection` rather than reimplemented by either.
 *
 * A fix that lands here lands for every channel built on it. Before this was
 * extracted, `DeploymentConnection` carried a fix `RunConnection` did not:
 * `onAttempt`, added so a chip could notice a second and third consecutive
 * failure that `onState` alone never re-announces (`#setState` drops a call
 * that would not change the state string). Nothing stopped the same gap from
 * reopening the next time either copy changed on its own; sharing the engine
 * is what makes "one fix, both channels" a structural fact rather than a
 * habit to remember.
 */
export class ReconnectingChannel<E> {
  readonly #options: ChannelOptions<E>;
  readonly #scheduler: Scheduler;
  readonly #visibility: Visibility;

  #handle: StreamHandle | null = null;
  #cancelRetry: (() => void) | null = null;
  #cancelFlush: (() => void) | null = null;
  #flushDue = false;
  #stopWatching: (() => void) | null = null;
  #buffered: E[] = [];
  #state: ConnectionState = 'disconnected';
  /** What it was doing before the tab went away, to be restored on return. */
  #resting: ConnectionState = 'disconnected';
  #attempts = 0;
  #exhausted = false;
  #closed = false;
  /** A reconnection that is owed but must not happen while nobody is looking. */
  #owed = false;

  constructor(options: ChannelOptions<E>) {
    this.#options = options;
    this.#scheduler = options.scheduler ?? wallClock;
    this.#visibility = options.visibility ?? documentVisibility;
  }

  get state(): ConnectionState {
    return this.#state;
  }

  /** How many reconnections have been attempted since the last delivery. */
  get attempts(): number {
    return this.#attempts;
  }

  /** Whether the bound was reached, which is when a manual reload is offered. */
  get exhausted(): boolean {
    return this.#exhausted;
  }

  /** Start reading, and start listening for the tab going away and coming back. */
  open(): void {
    if (this.#closed || this.#stopWatching !== null) return;
    this.#stopWatching = this.#visibility.onChange(() => {
      this.#visibilityChanged();
    });
    this.#connect();
  }

  /**
   * Stop, completely.
   *
   * Every one of the four things this holds is released here — the stream, the
   * retry, the flush and the visibility listener — because a leak test counts
   * all four and a screen that unmounts is a screen that has gone.
   */
  close(): void {
    this.#closed = true;
    this.#owed = false;
    this.#tearDown();
    this.#stopWatching?.();
    this.#stopWatching = null;
    this.#buffered = [];
    this.#setState('disconnected');
  }

  #tearDown(): void {
    this.#handle?.close();
    this.#handle = null;
    this.#cancelRetry?.();
    this.#cancelRetry = null;
    this.#cancelFlush?.();
    this.#cancelFlush = null;
    this.#flushDue = false;
  }

  #setState(state: ConnectionState): void {
    if (this.#state === state) return;
    this.#state = state;
    this.#options.onState(state);
  }

  #connect(): void {
    if (this.#closed) return;
    this.#cancelRetry?.();
    this.#cancelRetry = null;
    this.#handle?.close();

    this.#setState(this.#attempts === 0 ? 'connecting' : 'reconnecting');
    // Whether this attempt is a reopen is decided here rather than inside
    // `onOpen`, because `#flush` puts the attempt count back to nought the
    // moment anything arrives — a frame delivered before the transport
    // reports the open would otherwise turn a reconnection into a first
    // connection and swallow the gap it left.
    const reopening = this.#attempts > 0;
    const address = this.#options.address();
    this.#handle = this.#options.source.open(address, {
      onOpen: () => {
        if (this.#closed || this.#visibility.hidden()) return;
        this.#setState('connected');
        // A tab that went to the background between the attempt and the open
        // is left to the caller's own fallback, which is running precisely
        // because the state never reached `connected`.
        if (reopening) this.#options.onReconnect?.();
      },
      onFrame: (data) => {
        this.#received(data);
      },
      onError: (status) => {
        this.#failed(status);
      },
    });
  }

  #received(data: string): void {
    if (this.#closed) return;
    const event = this.#options.decode(data);
    // A keep-alive and a frame this console cannot read both cost one line of
    // the transcript rather than the rest of the stream.
    if (event === null) return;
    if (this.#options.isImmediate?.(event) === true) {
      // Not batched: a confession, not a fact to accumulate alongside
      // whatever else arrived, so it is acted on immediately.
      this.#options.onImmediate?.(event);
      return;
    }
    this.#buffered.push(event);
    if (this.#visibility.hidden()) return;
    if (this.#flushDue) return;
    // Scheduled rather than applied here, so a burst of ten thousand events is
    // one pass through the reducer and one render instead of ten thousand.
    this.#scheduleFlush();
  }

  /**
   * Ask for a flush, without assuming the scheduler is asynchronous.
   *
   * A scheduler that runs the callback immediately would otherwise leave the
   * cancel handle of a flush that has already happened lying in the field, and
   * every later event would see it and decline to schedule anything — one event
   * applied and the rest of the run silently buffered.
   */
  #scheduleFlush(): void {
    this.#flushDue = true;
    const already = { run: false };
    const cancel = this.#scheduler.after(this.#options.batchDelayMs ?? 0, () => {
      already.run = true;
      this.#flushDue = false;
      this.#cancelFlush = null;
      this.#flush();
    });
    if (!already.run) this.#cancelFlush = cancel;
  }

  #flush(): void {
    this.#cancelFlush = null;
    this.#flushDue = false;
    if (this.#closed || this.#buffered.length === 0) return;
    const batch = this.#buffered;
    this.#buffered = [];
    // Something arrived, so whatever went wrong before is over. A stream
    // that keeps breaking after every event is a different failure from one
    // that will not open at all.
    this.#attempts = 0;
    this.#setState('connected');
    this.#options.onEvents(batch);
  }

  #failed(status: number): void {
    if (this.#closed) return;
    this.#tearDown();

    if (status === 401) {
      // Not a stream failure. A session that ended mid-stream ends the session,
      // through the one controller every other refusal reaches, so three
      // concurrent refusals still produce one prompt.
      this.#setState('disconnected');
      reportUnauthorized();
      return;
    }

    this.#attempts += 1;
    this.#options.onAttempt?.(this.#attempts);
    if (this.#attempts > MAX_RECONNECTIONS) {
      this.#exhausted = true;
      this.#setState('disconnected');
      return;
    }

    if (this.#visibility.hidden()) {
      // Owed rather than scheduled: no timer runs for a screen nobody is
      // looking at, and the reconnection happens the moment they come back.
      this.#owed = true;
      this.#setState('idle');
      return;
    }

    this.#setState('reconnecting');
    const wait = BACKOFF_MS[Math.min(this.#attempts - 1, BACKOFF_MS.length - 1)] ?? 0;
    const already = { run: false };
    const cancel = this.#scheduler.after(wait, () => {
      already.run = true;
      this.#connect();
    });
    // Same guard as the flush: a scheduler that runs immediately must not leave
    // the handle of a retry that has already happened behind it.
    if (!already.run) this.#cancelRetry = cancel;
  }

  #visibilityChanged(): void {
    if (this.#closed) return;
    if (this.#visibility.hidden()) {
      this.#resting = this.#state;
      this.#cancelFlush?.();
      this.#cancelFlush = null;
      this.#setState('idle');
      return;
    }

    this.#setState(this.#resting === 'idle' ? 'connecting' : this.#resting);
    if (this.#owed) {
      this.#owed = false;
      this.#connect();
      return;
    }
    if (this.#buffered.length === 0) return;
    // Everything that arrived while the tab was away, applied once, in order.
    this.#cancelFlush = this.#scheduler.after(0, () => {
      this.#flush();
    });
  }
}

export interface RunConnectionOptions {
  readonly runId: string;
  readonly source: StreamSource;
  /** The cursor to present, read at connect time from whatever holds the state. */
  readonly cursor: () => string;
  readonly onState: (state: ConnectionState) => void;
  readonly onEvents: (events: readonly StreamEvent[]) => void;
  /**
   * See `ChannelOptions.onAttempt`. Nothing reads this on a run connection
   * today — the transcript's own badge (`connection-state.tsx`) shows one
   * word per state, never a count — but the hook exists here too, because
   * `RunConnection` and `DeploymentConnection` now share the one engine that
   * raises it; a future reader of `.attempts` gets the fix for free instead
   * of having to reinvent it the way `DeploymentConnection` once did alone.
   */
  readonly onAttempt?: (attempts: number) => void;
  readonly scheduler?: Scheduler;
  readonly visibility?: Visibility;
}

/**
 * One run's stream: `ReconnectingChannel` opened at this run's own address —
 * recomputed from its cursor on every attempt — and fed this run's own frame
 * format.
 */
export class RunConnection extends ReconnectingChannel<StreamEvent> {
  constructor(options: RunConnectionOptions) {
    super({
      source: options.source,
      address: () => streamAddress(options.runId, options.cursor()),
      decode: eventFromFrame,
      onState: options.onState,
      onEvents: options.onEvents,
      ...(options.onAttempt === undefined ? {} : { onAttempt: options.onAttempt }),
      ...(options.scheduler === undefined ? {} : { scheduler: options.scheduler }),
      ...(options.visibility === undefined ? {} : { visibility: options.visibility }),
    });
  }
}
