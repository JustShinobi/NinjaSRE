/**
 * What a run did, as one sequence of events — and the two shapes it arrives in.
 *
 * The console has **one** transcript. Whether the events came from a replay call
 * or from a live stream is the caller's problem, and the component downstream of
 * this module cannot tell the difference because there is nothing in a
 * `TranscriptEvent` that says where it came from.
 *
 * That is worth stating as a design decision rather than a convenience, because
 * the failure it prevents is specific and common: a live view and a history view
 * are two obvious files, they diverge within a month, and the divergence is
 * always in the direction of the live one showing something the recorded one
 * cannot. A run that is being watched and the same run read back tomorrow have to
 * be the same account of the same events, or the recorded one is not evidence.
 *
 * `tests/unit/surfaces/transcript.test.tsx` holds the structural half: exactly
 * one component in this console renders these.
 */

/**
 * Every kind of thing a run does, distinguished semantically rather than by
 * colour.
 *
 * The set is closed. An event kind the console has never heard of becomes
 * `reasoning` with its own raw label rather than disappearing — a deployment one
 * version ahead is not a fault, and an event silently dropped from a transcript
 * is evidence silently dropped from a record.
 */
export const TRANSCRIPT_KINDS = [
  'objective',
  'reasoning',
  'call',
  'result',
  'evidence',
  'recall',
  'dispatch',
  'return',
  'guardrail',
  'interaction',
  'report',
] as const;

export type TranscriptKind = (typeof TRANSCRIPT_KINDS)[number];

/** One thing that happened, in the form the transcript renders. */
export interface TranscriptEvent {
  readonly id: string;
  readonly kind: TranscriptKind;
  /** The kind as the deployment spelled it, for one it does not know. */
  readonly rawKind: string;
  /** ISO 8601, or empty when the source carried no instant. */
  readonly at: string;
  /** The heading of the entry: a capability's name, a turn's number, a verdict. */
  readonly title: string;
  /** The prose. What the agent concluded, what the guardrail withheld. */
  readonly detail: string;
  /**
   * The deployment's own note about this event, never the model's words.
   *
   * A turn's selection rationale lives here: it is generated prose full of
   * capability names, it repeats almost verbatim between turns because the
   * scoring is deterministic, and it is the answer to a question — "why was
   * this capability not offered" — nobody asks until something has gone wrong.
   * So it is carried apart from `detail`, drawn folded, and never run through
   * the markdown renderer, which would eat the underscores out of every
   * capability name it contains.
   */
  readonly note: string;
  /** Arguments or a result, bounded when rendered. */
  readonly payload: string;
  /** A capability call's outcome. Empty when the event is not a call. */
  readonly status: string;
  /** How long a call took, in milliseconds. Zero when it is not a call. */
  readonly durationMs: number;
}

/** Which semantic weight each kind is drawn at. */
export const KIND_ROLE: Readonly<Record<TranscriptKind, string>> = {
  objective: 'info',
  reasoning: 'neutral',
  call: 'neutral',
  result: 'neutral',
  evidence: 'info',
  recall: 'info',
  dispatch: 'info',
  return: 'info',
  // The most important line in most transcripts, and it must not read as an
  // aside: an action that was withheld is the whole reason a person is reading.
  guardrail: 'danger',
  interaction: 'warning',
  report: 'success',
};

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

function list(record: unknown, name: string): readonly unknown[] {
  const found = field(record, name);
  return Array.isArray(found) ? found : [];
}

/** A payload, as the text a reader sees. Stable key order, so two runs compare. */
function payloadOf(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, Object.keys(value).sort(), 2);
}

/**
 * Which kind a streamed event's name is.
 *
 * A table rather than a chain of conditions, because the set is the contract
 * with the deployment and a table is a thing somebody can read against it.
 */
const STREAM_KINDS: Readonly<Record<string, TranscriptKind>> = {
  run_started: 'objective',
  turn_started: 'reasoning',
  model_reasoned: 'reasoning',
  tool_called: 'call',
  tool_succeeded: 'result',
  tool_failed: 'result',
  observation_recorded: 'evidence',
  evidence_retained: 'evidence',
  memory_recalled: 'recall',
  subagent_dispatched: 'dispatch',
  subagent_returned: 'return',
  guardrail_withheld: 'guardrail',
  guardrail_applied: 'guardrail',
  interaction_opened: 'interaction',
  interaction_answered: 'interaction',
  run_completed: 'report',
  run_failed: 'report',
};

/** The kind `name` is, or `reasoning` for one this console has not met. */
export function kindOf(name: string): TranscriptKind {
  return STREAM_KINDS[name] ?? 'reasoning';
}

interface Draft {
  readonly kind: TranscriptKind;
  readonly rawKind: string;
  readonly at?: string;
  readonly title: string;
  readonly detail?: string;
  readonly note?: string;
  readonly payload?: string;
  readonly status?: string;
  readonly durationMs?: number;
}

function event(id: string, draft: Draft): TranscriptEvent {
  return {
    id,
    kind: draft.kind,
    rawKind: draft.rawKind,
    at: draft.at ?? '',
    title: draft.title,
    detail: draft.detail ?? '',
    note: draft.note ?? '',
    payload: draft.payload ?? '',
    status: draft.status ?? '',
    durationMs: draft.durationMs ?? 0,
  };
}

/**
 * The events a *recorded* run carries, from the replay or threads body.
 *
 * A turn becomes the agent's reasoning about what to do next, and each call
 * under it becomes a call and its result. The two are separate events rather
 * than one because they are separate facts: what was asked for, and what came
 * back. A transcript that folded them together could not show a call that never
 * returned.
 */
export function eventsFromReplay(body: unknown): readonly TranscriptEvent[] {
  const events: TranscriptEvent[] = [];
  const runId = text(body, 'run_id');

  for (const turn of list(body, 'turns')) {
    const turnId = text(turn, 'turn_id');
    const index = count(turn, 'index');
    events.push(
      event(`${turnId}-reasoning`, {
        kind: 'reasoning',
        rawKind: 'turn',
        // The index the run recorded, unchanged. Adding one here made every
        // screen count from two: a five-turn investigation showed turns 2 to 6
        // and no turn 1 anywhere in the console.
        title: String(index),
        detail: text(turn, 'model_rationale'),
        note: text(turn, 'selection_rationale'),
        payload: text(turn, 'model'),
      }),
    );
    for (const call of list(turn, 'calls')) {
      const callId = text(call, 'call_id');
      const name = text(call, 'name');
      events.push(
        event(`${callId}-call`, {
          kind: 'call',
          rawKind: 'tool_called',
          title: name,
          payload: payloadOf(field(call, 'arguments')),
        }),
      );
      events.push(
        event(`${callId}-result`, {
          kind: 'result',
          rawKind: 'tool_returned',
          title: name,
          detail: text(call, 'error'),
          payload: payloadOf(field(call, 'result')),
          status: text(call, 'status'),
          durationMs: count(call, 'duration_ms'),
        }),
      );
    }
  }

  const summary = text(body, 'summary');
  if (summary !== '') {
    events.push(
      event(`${runId}-report`, {
        kind: 'report',
        rawKind: 'run_completed',
        title: runId,
        detail: summary,
      }),
    );
  }
  return events;
}

/**
 * One event of a live run, in the fields the stream carries it in.
 *
 * Named rather than taken as `unknown` because the live layer has already
 * parsed a frame by the time it gets here, and re-deriving the same five fields
 * from a raw document a second time is how two spellings of one event start.
 */
export interface StreamedEvent {
  readonly runId: string;
  readonly kind: string;
  readonly sequence: number;
  readonly occurredAt: string;
  readonly payload: unknown;
}

/**
 * One streamed event, in the form the transcript renders.
 *
 * The single point at which a live event becomes a transcript entry. Both
 * readers below it — the batch one and the live layer's reducer — go through
 * here, which is what makes "two readers, one vocabulary" a fact about the code
 * rather than a claim about the intention.
 */
export function eventFromStream(streamed: StreamedEvent): TranscriptEvent {
  const { kind: name, payload } = streamed;
  return event(`${streamed.runId}-${String(streamed.sequence)}`, {
    kind: kindOf(name),
    rawKind: name,
    at: streamed.occurredAt,
    title: text(payload, 'name') === '' ? name : text(payload, 'name'),
    detail:
      text(payload, 'detail') === ''
        ? text(payload, 'objective')
        : text(payload, 'detail'),
    payload: payloadOf(payload),
    status: text(payload, 'status'),
    durationMs: count(payload, 'duration_ms'),
  });
}

/**
 * The events a *live* run carries, from the stream body.
 *
 * The same shape out. This is the whole claim the single-component rule rests
 * on: two readers, one vocabulary, and nothing downstream that can tell which
 * reader it was handed.
 */
export function eventsFromStream(body: unknown): readonly TranscriptEvent[] {
  return list(body, 'events').map((raw) =>
    eventFromStream({
      runId: text(raw, 'run_id'),
      kind: text(raw, 'kind'),
      sequence: count(raw, 'sequence'),
      occurredAt: text(raw, 'occurred_at'),
      payload: field(raw, 'payload'),
    }),
  );
}

/** One model's share of a run, for the cost breakdown. */
export interface ModelUsage {
  readonly model: string;
  readonly turns: number;
  readonly tokens: number;
  readonly cost: number;
}

/** One turn's share of a run. */
export interface TurnUsage {
  readonly turn: number;
  readonly model: string;
  readonly calls: number;
  readonly tokens: number;
  readonly cost: number;
}

/** What a run cost, split the two ways an operator asks about it. */
export interface RunUsage {
  readonly tokens: number;
  readonly cost: number;
  /**
   * How many turns carried no recorded price.
   *
   * The distinction this exists to keep: a run whose provider publishes no
   * price for its model is not a run that cost nothing. Reading `cost` alone
   * prints a confident `$0.00` beside tens of thousands of tokens, which is
   * the one reading that is certainly false.
   */
  readonly unpricedTurns: number;
  /** Whether every turn of this run carried a price. */
  readonly priced: boolean;
  readonly byModel: readonly ModelUsage[];
  readonly byTurn: readonly TurnUsage[];
}

/**
 * A run's cost and tokens, by model and by turn.
 *
 * Apportioned by turn count rather than reported per turn, because the replay
 * carries one total and a list of turns. That is stated on the screen — a
 * breakdown presented as measurement when it is division is a number somebody
 * will chase a discrepancy in for an afternoon.
 */
export function usageFrom(body: unknown): RunUsage {
  const turns = list(body, 'turns');
  const tokens = count(body, 'total_tokens');
  const cost = count(body, 'total_cost');
  const share = turns.length === 0 ? 0 : 1 / turns.length;

  const unpricedTurns = count(body, 'unpriced_turns');
  const byTurn: TurnUsage[] = turns.map((turn) => ({
    // The index the run recorded. Adding one made the cost table count from
    // two, so a five-turn run listed turns 2 to 6 beside a transcript that
    // agreed with it and a store that did not.
    turn: count(turn, 'index'),
    model: text(turn, 'model'),
    calls: list(turn, 'calls').length,
    tokens: tokens * share,
    cost: cost * share,
  }));

  const models = new Map<string, ModelUsage>();
  for (const turn of byTurn) {
    const held = models.get(turn.model);
    models.set(turn.model, {
      model: turn.model,
      turns: (held?.turns ?? 0) + 1,
      tokens: (held?.tokens ?? 0) + turn.tokens,
      cost: (held?.cost ?? 0) + turn.cost,
    });
  }

  return {
    tokens,
    cost,
    unpricedTurns,
    priced: turns.length > 0 && unpricedTurns === 0,
    byModel: [...models.values()],
    byTurn,
  };
}
