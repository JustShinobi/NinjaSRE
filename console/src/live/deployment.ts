import {
  ReconnectingChannel,
  type ConnectionState,
  type Scheduler,
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
 * **Reuse, structural rather than declared.** `DeploymentConnection` is
 * `connection.ts`'s own `ReconnectingChannel` — the exact engine
 * `RunConnection` is also built from — opened at this channel's fixed
 * address, decoding this channel's own frame shape, batching for
 * `DEPLOYMENT_REFRESH_BATCH_MS` instead of applying on the next scheduler
 * tick, and routing one event (`resync`) around the batch entirely instead
 * of through it. State, teardown, the backoff table, the ten-attempt bound
 * and pausing for a hidden tab are the shared engine's, not a second copy of
 * either — the two classes below are the whole of what is left over once
 * that is factored out.
 *
 * **No cursor is presented on reconnect, and the reopen is announced
 * instead.** `RunConnection` remembers a position so a reconnection resumes
 * at the event after the last one applied; this connection remembers
 * nothing, so a drop is a hole in what it saw. The hole is closed by
 * `onReconnect`: the channel says it re-opened, and this channel's reader
 * answers that the way it answers everything else, with a single
 * `router.refresh()` that reads the truth back from the routes that own it.
 *
 * That is deliberately cheaper than a cursor and strictly wider. A cursor
 * would depend on the broker still holding the events in memory and would
 * have to be carried through the courier route on every attempt; announcing
 * the reopen depends on nothing and covers a drop of any length. What it
 * costs is one extra re-read after a drop that happened to carry nothing —
 * which is the same re-read the fallback timer would have made anyway.
 *
 * The claim this paragraph used to make — that a first connection's silence
 * already ends in a `router.refresh()`, so a reconnection needs no signal —
 * was false, and false in the direction that loses events. A first
 * connection's silence ends in *no* action at all, correctly: the page was
 * server-rendered moments before. A reconnection's silence is a gap, and
 * before `onReconnect` existed it ended in no action either, so anything
 * published during a drop shorter than the fallback interval was lost
 * permanently while the chip still read `live`. FR-004's guarantee that a
 * *presented* cursor never double-delivers remains a contract-level property
 * (`tests/contract/gateway/test_deployment_stream.py`), unaffected either
 * way.
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
  /**
   * The channel dropped and is back, so whatever was published in between
   * was missed. Required rather than optional — like `onResync`, and unlike
   * `ChannelOptions.onReconnect`, which a run's stream rightly leaves unset:
   * this channel presents no cursor, so every reader of it has to answer
   * what it does about a gap, and the type is what asks.
   */
  readonly onReconnect: () => void;
  /**
   * See `ChannelOptions.onAttempt`. This channel's own chip reads it, to
   * decide when a retry has gone on long enough to call it `stale` rather
   * than `refreshing`.
   */
  readonly onAttempt?: (attempts: number) => void;
  readonly scheduler?: Scheduler;
  readonly visibility?: Visibility;
}

/**
 * The deployment channel: `ReconnectingChannel` opened at a fixed address,
 * decoding this channel's own frame shape, and batched over a window instead
 * of the next scheduler tick — with `resync` bypassing that batch entirely.
 */
export class DeploymentConnection extends ReconnectingChannel<DeploymentEvent> {
  constructor(options: DeploymentConnectionOptions) {
    super({
      source: options.source,
      address: () => DEPLOYMENT_STREAM_ADDRESS,
      decode: deploymentEventFromFrame,
      batchDelayMs: DEPLOYMENT_REFRESH_BATCH_MS,
      isImmediate: (event) => event.kind === RESYNC_KIND,
      onImmediate: () => {
        options.onResync();
      },
      onState: options.onState,
      onEvents: options.onEvents,
      onReconnect: options.onReconnect,
      ...(options.onAttempt === undefined ? {} : { onAttempt: options.onAttempt }),
      ...(options.scheduler === undefined ? {} : { scheduler: options.scheduler }),
      ...(options.visibility === undefined ? {} : { visibility: options.visibility }),
    });
  }
}
