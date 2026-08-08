import { eventFromStream, type TranscriptEvent } from '@/surfaces/transcript';
import { cursorOf, NOTHING_SEEN } from './cursor';
import type { StreamEvent } from './events';

/**
 * What a live run looks like, as a pure function of what has arrived.
 *
 * No DOM, no timer, no network, no React. That is the whole reason this module
 * exists separately from the transport: exactly-once delivery across a
 * reconnection is the hardest property here and the easiest to break, and a
 * pure `(state, event) => state` makes it provable in a unit test against a
 * source that raises, replays and reorders — rather than something a browser
 * test observes happening most of the time.
 *
 * Three rules do the work, and each of them makes a class of failure impossible
 * rather than unlikely:
 *
 * - **A sequence at or below the cursor is discarded.** Duplicates are harmless
 *   by construction, so the deployment never has to promise not to send one —
 *   and after a reconnection it always does, because the catch-up read is
 *   inclusive of the position the client presented.
 * - **A sequence beyond the next one is held, not rendered.** A transcript with
 *   a hole in it is a transcript somebody reads the wrong conclusion out of.
 *   The gap fills, and the held events are released in order in one pass.
 * - **The cursor is the last event actually applied**, never the last one
 *   received. A cursor that ran ahead of the transcript would resume past
 *   something nobody ever saw.
 */

/** One applied event, with the position it holds in the run's log. */
export interface LiveEvent extends TranscriptEvent {
  readonly sequence: number;
}

/** Whether the run is still going, and how it stopped if it is not. */
export const RUN_PHASES = ['running', 'completed', 'failed', 'cancelled'] as const;

export type RunPhase = (typeof RUN_PHASES)[number];

/**
 * The event kind that closes an interaction, and the one that opens one.
 *
 * The deployment's vocabulary, not this console's. `attention_changed` is the
 * only kind that closes a card — an approval being *raised* also concerns an
 * interaction, and treating any attention change as a closure would make a card
 * vanish at the moment it became relevant.
 */
export const CLOSING_KIND = 'attention_changed';
export const OPENING_KIND = 'approval_requested';

/** The kinds after which nothing further arrives for this run. */
export const TERMINAL_KINDS: readonly string[] = [
  // What the deployment records.
  'run_finished',
  'run_interrupted',
  // What a stream one version ahead may spell them as. Listed rather than
  // guessed at: a terminal event the console does not recognise leaves a
  // finished run presenting itself as live for ever, which is the one thing
  // FR-005 exists to rule out.
  'run_completed',
  'run_failed',
  'run_cancelled',
];

/** What a run reported as it finished, mapped onto how the view reads. */
const FINISHED_PHASE: Readonly<Record<string, RunPhase>> = {
  succeeded: 'completed',
  completed: 'completed',
  failed: 'failed',
  errored: 'failed',
  cancelled: 'cancelled',
  interrupted: 'cancelled',
};

/** One thing the run is waiting on a person for. */
export interface Waiting {
  readonly id: string;
  readonly kind: 'question' | 'approval';
  /** What is being asked, as the deployment phrased it. */
  readonly question: string;
  readonly options: readonly string[];
  /** Whether it still needs somebody. A closed one stays, marked. */
  readonly open: boolean;
  readonly since: string;
}

/** Who decided one, where, and which way. */
export interface Decision {
  readonly id: string;
  /** Empty when the deployment did not say. Never guessed at. */
  readonly decidedBy: string;
  /** The surface it was decided on — chat, the CLI, another browser. */
  readonly surface: string;
  readonly verdict: string;
  readonly at: string;
}

/** One run, as everything that has arrived so far leaves it. */
export interface LiveState {
  readonly runId: string;
  /** The last sequence applied, or `NOTHING_SEEN`. */
  readonly position: number;
  /** What a reconnection presents. Empty for a client that has seen nothing. */
  readonly cursor: string;
  readonly events: readonly LiveEvent[];
  /** Arrived early, waiting for the gap before them to fill. */
  readonly held: readonly StreamEvent[];
  readonly phase: RunPhase;
  readonly waiting: readonly Waiting[];
  readonly decided: readonly Decision[];
  /** How many events have been applied, which is what a burst test counts. */
  readonly applied: number;
}

/** What a screen already knows before the stream is opened. */
export interface Seed {
  readonly events?: readonly LiveEvent[];
  readonly position?: number;
  readonly phase?: RunPhase;
  readonly waiting?: readonly Waiting[];
}

/**
 * A run, before anything has arrived.
 *
 * The seed is how a live view starts from what the server already rendered:
 * the replay is on screen, its last sequence is the cursor, and the stream
 * fills in from there rather than sending the whole run again.
 */
export function openRun(runId: string, seed: Seed = {}): LiveState {
  const position = seed.position ?? NOTHING_SEEN;
  return {
    runId,
    position,
    cursor: cursorOf(runId, position),
    events: seed.events ?? [],
    held: [],
    phase: seed.phase ?? 'running',
    waiting: seed.waiting ?? [],
    decided: [],
    applied: 0,
  };
}

/** Whether this run has stopped, whichever way it stopped. */
export function isTerminal(state: LiveState): boolean {
  return state.phase !== 'running';
}

/** The interaction `id` names, open or closed, or nothing. */
export function waitingFor(state: LiveState, id: string): Waiting | undefined {
  return state.waiting.find((item) => item.id === id);
}

/** How `id` was decided, or nothing when it has not been. */
export function decisionFor(state: LiveState, id: string): Decision | undefined {
  return state.decided.find((decision) => decision.id === id);
}

/** How many interactions are still waiting on somebody. */
export function openCount(state: LiveState): number {
  return state.waiting.filter((item) => item.open).length;
}

function field(record: unknown, name: string): unknown {
  return Reflect.get(Object(record), name);
}

function text(record: unknown, name: string): string {
  const found = field(record, name);
  return typeof found === 'string' ? found : '';
}

/**
 * The interaction an event is about.
 *
 * Several keys, because the vocabulary is the deployment's and an approval and
 * a question identify themselves differently.
 */
function subjectOf(payload: unknown): string {
  for (const key of ['interaction_id', 'approval_id']) {
    const found = text(payload, key);
    if (found !== '') return found;
  }
  return '';
}

function phaseAfter(phase: RunPhase, event: StreamEvent): RunPhase {
  if (!TERMINAL_KINDS.includes(event.kind)) return phase;
  if (event.kind === 'run_interrupted' || event.kind === 'run_cancelled')
    return 'cancelled';
  if (event.kind === 'run_failed') return 'failed';
  if (event.kind === 'run_completed') return 'completed';
  return FINISHED_PHASE[text(event.payload, 'status')] ?? 'completed';
}

function waitingAfter(
  waiting: readonly Waiting[],
  event: StreamEvent,
): readonly Waiting[] {
  const id = subjectOf(event.payload);
  if (id === '') return waiting;

  if (event.kind === OPENING_KIND || event.kind === 'interaction_opened') {
    if (waiting.some((item) => item.id === id)) return waiting;
    const options = field(event.payload, 'options');
    return [
      ...waiting,
      {
        id,
        kind: event.kind === OPENING_KIND ? 'approval' : 'question',
        question:
          text(event.payload, 'summary') === ''
            ? text(event.payload, 'text')
            : text(event.payload, 'summary'),
        options: Array.isArray(options) ? options.map(String) : [],
        open: true,
        since: event.occurredAt,
      },
    ];
  }

  if (!closes(event)) return waiting;
  // Marked rather than removed. A card that disappeared would leave the person
  // who was about to answer it wondering what they had just pressed.
  return waiting.map((item) => (item.id === id ? { ...item, open: false } : item));
}

/**
 * Whether this event says an interaction stopped needing a person.
 *
 * `attention_changed` with `waiting` true is the run *starting* to wait, which
 * closes nothing.
 */
function closes(event: StreamEvent): boolean {
  if (event.kind !== CLOSING_KIND && event.kind !== 'interaction_answered')
    return false;
  return field(event.payload, 'waiting') !== true;
}

function decidedAfter(
  decided: readonly Decision[],
  event: StreamEvent,
): readonly Decision[] {
  if (!closes(event)) return decided;
  const id = subjectOf(event.payload);
  if (id === '' || decided.some((decision) => decision.id === id)) return decided;
  return [
    ...decided,
    {
      id,
      decidedBy: text(event.payload, 'decided_by'),
      surface: text(event.payload, 'decided_on'),
      verdict: text(event.payload, 'verdict'),
      at: event.occurredAt,
    },
  ];
}

/**
 * `state` with every event in `incoming` applied.
 *
 * A batch rather than a loop over `applyEvent`, and that is a performance
 * property with a requirement behind it: ten thousand events after a long
 * disconnection would be ten thousand copies of a growing array if each were
 * applied on its own. Here the whole burst is ordered once, de-duplicated once,
 * and appended once.
 */
export function applyEvents(
  state: LiveState,
  incoming: readonly StreamEvent[],
): LiveState {
  const pool = new Map<number, StreamEvent>();
  for (const held of state.held) pool.set(held.sequence, held);
  const before = pool.size;

  for (const event of incoming) {
    // Another run's event is not this run's, whatever its sequence says.
    if (event.runId !== state.runId) continue;
    // At or below the cursor: already applied, and applying it again is what
    // the cursor exists to make impossible.
    if (event.sequence <= state.position) continue;
    if (pool.has(event.sequence)) continue;
    pool.set(event.sequence, event);
  }

  if (pool.size === before && !pool.has(state.position + 1)) return state;

  let position = state.position;
  let phase = state.phase;
  let waiting = state.waiting;
  let decided = state.decided;
  const appended: LiveEvent[] = [];

  // Released in order, and only while the next one is actually there.
  for (
    let next = pool.get(position + 1);
    next !== undefined;
    next = pool.get(position + 1)
  ) {
    pool.delete(next.sequence);
    position = next.sequence;
    appended.push({ ...eventFromStream(next), sequence: next.sequence });
    phase = phaseAfter(phase, next);
    waiting = waitingAfter(waiting, next);
    decided = decidedAfter(decided, next);
  }

  if (appended.length === 0 && pool.size === before) return state;

  return {
    runId: state.runId,
    position,
    cursor: cursorOf(state.runId, position),
    events: appended.length === 0 ? state.events : [...state.events, ...appended],
    held: [...pool.values()].sort((first, second) => first.sequence - second.sequence),
    phase,
    waiting,
    decided,
    applied: state.applied + appended.length,
  };
}

/** `state` with one event applied. */
export function applyEvent(state: LiveState, event: StreamEvent): LiveState {
  return applyEvents(state, [event]);
}
