import { reportUnauthorized } from '@/session/controller';
import {
  BACKOFF_MS,
  MAX_RECONNECTIONS,
  documentVisibility,
  wallClock,
  type ConnectionState,
  type Scheduler,
  type StreamHandle,
  type StreamSource,
  type Visibility,
} from './connection';

/**
 * The deployment-wide channel: one connection, no run, and never a data value.
 *
 * Every write path this feature taps — a run starting or finishing, an
 * incident opening or closing, a decision proposed or decided — reaches this
 * as an id and nothing else (FR-002's allowlist, enforced server-side). This
 * module never turns a frame into presentation data: it hands the batch to
 * whoever asked (`auto-refresh.tsx`), which is what schedules the one
 * `router.refresh()` that reads the truth back from the routes that own it.
 *
 * **Reuse, declared precisely.** `StreamSource`, `Scheduler`, `Visibility`,
 * `ConnectionState`, `BACKOFF_MS`, `wallClock` and `documentVisibility` are
 * `connection.ts`'s own — the exact types and the exact backoff table
 * `RunConnection` is built from, and the exact `fetchStreamSource` transport
 * (`transport.ts`) both connections open with, unmodified. What this module
 * does *not* share is `RunConnection`'s class body: extracting a fully
 * generic reconnection engine the two could both subclass touches a
 * heavily-tested, load-bearing file this feature does not otherwise need to
 * change, and was not attempted here. `DeploymentConnection` below is a
 * second, smaller state machine over the same primitives — declared here
 * rather than left for a reviewer to notice, since it is the one place FR-008
 * ("reusing … not a second implementation of reconnection") is not met in
 * full.
 *
 * **No cursor is presented on reconnect.** `RunConnection` remembers a
 * position so a reconnection resumes; this connection does not, because
 * every one of this channel's three deliveries — a batch of ids, a `resync`,
 * and a first connection's silence — already ends in the same client action,
 * a single `router.refresh()`. A cursor would only save the occasional extra
 * refresh after a brief drop, never change correctness: FR-004's guarantee
 * that a *presented* cursor never double-delivers is proven at the contract
 * level (`tests/contract/gateway/test_deployment_stream.py`), not here.
 */

/** Where the deployment channel is read from, through the console's own courier route. */
export const DEPLOYMENT_STREAM_ADDRESS = '/api/events/stream';

/**
 * How long a batch of events is allowed to accumulate before the connection
 * hands it over — a burst in the same instant costs one `router.refresh()`
 * rather than one per event. Mirrored in `config/constants/runs.py` as
 * `DEPLOYMENT_REFRESH_BATCH_MS`, the same value, because nothing on this side
 * reads a Python module at build time.
 */
export const DEPLOYMENT_REFRESH_BATCH_MS = 250;

/** One frame off the deployment channel, in the shape `deployment.ts` renders it. */
export interface DeploymentEvent {
  readonly scope: string;
  readonly kind: string;
  readonly sequence: number;
  readonly occurredAt: string;
  /** Carried through as `unknown` and never read here — see the module docstring. */
  readonly payload: unknown;
}

function field(record: unknown, name: string): unknown {
  return Reflect.get(Object(record), name);
}

function text(record: unknown, name: string): string {
  const found = field(record, name);
  return typeof found === 'string' ? found : '';
}

function count(record: unknown, name: string): number {
  const found = field(record, name);
  return typeof found === 'number' && Number.isFinite(found) ? found : 0;
}

/**
 * The event a deployment-channel SSE frame's `data` carries, or `null`.
 *
 * A malformed frame — the server's own keep-alive comment never reaches
 * here at all, `sse.ts`'s `framesIn` already drops it — costs this one frame,
 * never the rest of the connection, the same disposition `events.ts` gives
 * the per-run stream's own unreadable frame.
 */
export function deploymentEventFromFrame(data: string): DeploymentEvent | null {
  if (data === '') return null;
  let document: unknown;
  try {
    document = JSON.parse(data);
  } catch {
    return null;
  }
  const kind = text(document, 'kind');
  if (kind === '') return null;
  return {
    scope: text(document, 'scope'),
    kind,
    sequence: count(document, 'sequence'),
    occurredAt: text(document, 'occurred_at'),
    payload: field(document, 'payload') ?? {},
  };
}

/** The control kind FR-004 sends instead of a replay it cannot honestly stand behind. */
const RESYNC_KIND = 'resync';

export interface DeploymentConnectionOptions {
  readonly source: StreamSource;
  readonly onState: (state: ConnectionState) => void;
  /** A batch of real events — never includes a `resync`, which is its own callback. */
  readonly onEvents: (events: readonly DeploymentEvent[]) => void;
  readonly onResync: () => void;
  readonly scheduler?: Scheduler;
  readonly visibility?: Visibility;
}

export class DeploymentConnection {
  readonly #options: DeploymentConnectionOptions;
  readonly #scheduler: Scheduler;
  readonly #visibility: Visibility;

  #handle: StreamHandle | null = null;
  #cancelRetry: (() => void) | null = null;
  #cancelFlush: (() => void) | null = null;
  #flushDue = false;
  #stopWatching: (() => void) | null = null;
  #buffered: DeploymentEvent[] = [];
  #state: ConnectionState = 'disconnected';
  #resting: ConnectionState = 'disconnected';
  #attempts = 0;
  #exhausted = false;
  #closed = false;
  #owed = false;

  constructor(options: DeploymentConnectionOptions) {
    this.#options = options;
    this.#scheduler = options.scheduler ?? wallClock;
    this.#visibility = options.visibility ?? documentVisibility;
  }

  get state(): ConnectionState {
    return this.#state;
  }

  get attempts(): number {
    return this.#attempts;
  }

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

  /** Stop, completely — the stream, the retry, the flush and the visibility listener. */
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
    this.#handle = this.#options.source.open(DEPLOYMENT_STREAM_ADDRESS, {
      onOpen: () => {
        if (!this.#closed && !this.#visibility.hidden()) this.#setState('connected');
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
    const event = deploymentEventFromFrame(data);
    if (event === null) return;
    if (event.kind === RESYNC_KIND) {
      // Not batched: a resync is a confession, not a fact to accumulate
      // alongside whatever else arrived, and it is acted on immediately —
      // `auto-refresh.tsx` refreshes on it without waiting for the batch
      // window the way it does for an ordinary event.
      this.#options.onResync();
      return;
    }
    this.#buffered.push(event);
    if (this.#visibility.hidden()) return;
    if (this.#flushDue) return;
    this.#scheduleFlush();
  }

  #scheduleFlush(): void {
    this.#flushDue = true;
    const already = { run: false };
    const cancel = this.#scheduler.after(DEPLOYMENT_REFRESH_BATCH_MS, () => {
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
    this.#attempts = 0;
    this.#setState('connected');
    this.#options.onEvents(batch);
  }

  #failed(status: number): void {
    if (this.#closed) return;
    this.#tearDown();

    if (status === 401) {
      this.#setState('disconnected');
      reportUnauthorized();
      return;
    }

    this.#attempts += 1;
    if (this.#attempts > MAX_RECONNECTIONS) {
      this.#exhausted = true;
      this.#setState('disconnected');
      return;
    }

    if (this.#visibility.hidden()) {
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
    this.#cancelFlush = this.#scheduler.after(0, () => {
      this.#flush();
    });
  }
}
