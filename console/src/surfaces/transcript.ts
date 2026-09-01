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

import { message, type Locale, type MessageKey } from '@/i18n/messages';

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
 *
 * Exported for the narration table below, which is keyed by exactly this set
 * of raw kinds, and for the completeness test that proves every one of them
 * has a phrase in every locale this console carries.
 */
export const STREAM_KINDS: Readonly<Record<string, TranscriptKind>> = {
  // The vocabulary the deployment emits — `TraceEventKind` in
  // `platform/runs/events.py`, the closed set the recorder actually writes.
  // A live run on staging narrated every one of these as "an unrecognised
  // kind arrived" while the table below carried only the older spellings.
  run_started: 'objective',
  stage_completed: 'reasoning',
  turn_completed: 'reasoning',
  capability_called: 'call',
  evidence_observed: 'evidence',
  subagent_dispatched: 'dispatch',
  guardrail_action: 'guardrail',
  masking_applied: 'guardrail',
  budget_eviction: 'guardrail',
  approval_requested: 'interaction',
  attention_changed: 'interaction',
  report_delivered: 'report',
  notification_decided: 'reasoning',
  run_interrupted: 'report',
  run_finished: 'report',
  // The mock dataset's own extra: a formed hypothesis is the model thinking.
  hypothesis_formed: 'reasoning',
  // Older spellings, kept as synonyms: they cost nothing and a replay
  // recorded before the vocabulary settled still renders under them.
  turn_started: 'reasoning',
  model_reasoned: 'reasoning',
  tool_called: 'call',
  tool_succeeded: 'result',
  tool_failed: 'result',
  observation_recorded: 'evidence',
  evidence_retained: 'evidence',
  memory_recalled: 'recall',
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
  // The field a name arrives under is the kind's own: the recorder writes a
  // call's name as `capability` and a stage boundary's as `stage`
  // (`platform/runs/recorder.py`). Falling through them in order, with the
  // raw kind last, keeps the meta line honest for an event that named nothing.
  const title =
    text(payload, 'name') || text(payload, 'capability') || text(payload, 'stage') || name;
  // Likewise the prose: a stage boundary carries what it established as
  // `finding`, and the mock dataset's hypothesis carries its `text`.
  const detail =
    text(payload, 'detail') ||
    text(payload, 'objective') ||
    text(payload, 'finding') ||
    text(payload, 'text');
  return event(`${streamed.runId}-${String(streamed.sequence)}`, {
    kind: kindOf(name),
    rawKind: name,
    at: streamed.occurredAt,
    title,
    detail,
    payload: payloadOf(payload),
    status: text(payload, 'status'),
    durationMs: count(payload, 'duration_ms'),
  });
}

/**
 * The lead sentence for each raw kind `STREAM_KINDS` declares.
 *
 * A message key per kind rather than a hand-written string, so both locales
 * carry it and a kind added to `STREAM_KINDS` with none here is caught by the
 * completeness test (`tests/unit/surfaces/transcript-narration.test.ts`)
 * rather than shown to an operator as its own raw name. The event's own
 * `detail` — the objective, the reasoning, the observation, the question —
 * is appended after the lead by `narrate` below rather than folded into the
 * template, so the template itself never needs the field to be non-empty.
 *
 * Two kinds take a `{name}`: the capability a call named, or the sub-agent a
 * dispatch named. Every other kind's lead is fixed, because the field
 * `eventFromStream` extracts as `title` for those kinds is not a name at
 * all — it is the raw kind itself, standing in for one that was never given.
 */
const NARRATION_LEAD: Readonly<Record<string, MessageKey>> = {
  run_started: 'transcript.narration.runStarted',
  stage_completed: 'transcript.narration.stageCompleted',
  turn_completed: 'transcript.narration.turnCompleted',
  // A live call names its capability under `capability`; the extraction above
  // already put it in `title`, so the stream's own lead phrase serves both.
  capability_called: 'transcript.narration.toolCalled',
  evidence_observed: 'transcript.narration.evidenceObserved',
  guardrail_action: 'transcript.narration.guardrailApplied',
  masking_applied: 'transcript.narration.maskingApplied',
  budget_eviction: 'transcript.narration.budgetEviction',
  approval_requested: 'transcript.narration.approvalRequested',
  attention_changed: 'transcript.narration.attentionChanged',
  report_delivered: 'transcript.narration.reportDelivered',
  notification_decided: 'transcript.narration.notificationDecided',
  run_interrupted: 'transcript.narration.runInterrupted',
  run_finished: 'transcript.narration.runFinished',
  hypothesis_formed: 'transcript.narration.hypothesisFormed',
  turn_started: 'transcript.narration.turnStarted',
  model_reasoned: 'transcript.narration.modelReasoned',
  tool_called: 'transcript.narration.toolCalled',
  tool_succeeded: 'transcript.narration.toolSucceeded',
  tool_failed: 'transcript.narration.toolFailed',
  // `eventsFromReplay` spells a call's outcome `tool_returned` rather than
  // splitting it into `tool_succeeded`/`tool_failed` the way the stream
  // does — the replay reader already carries the outcome in `status`
  // instead, which the Badge beside this sentence already draws. The lead
  // is the stream's own success wording, deliberately status-neutral: it
  // is true whichever way the call actually went, and is not the only
  // signal the reader has for which.
  tool_returned: 'transcript.narration.toolSucceeded',
  observation_recorded: 'transcript.narration.observationRecorded',
  evidence_retained: 'transcript.narration.evidenceRetained',
  memory_recalled: 'transcript.narration.memoryRecalled',
  subagent_dispatched: 'transcript.narration.subagentDispatched',
  subagent_returned: 'transcript.narration.subagentReturned',
  guardrail_withheld: 'transcript.narration.guardrailWithheld',
  guardrail_applied: 'transcript.narration.guardrailApplied',
  interaction_opened: 'transcript.narration.interactionOpened',
  interaction_answered: 'transcript.narration.interactionAnswered',
  run_completed: 'transcript.narration.runCompleted',
  run_failed: 'transcript.narration.runFailed',
};

/** The raw kinds whose lead names a capability, read from `event.title`. */
const NAMES_A_CAPABILITY: ReadonlySet<string> = new Set([
  'tool_called',
  'tool_succeeded',
  'tool_failed',
  'tool_returned',
  'capability_called',
]);

/** The raw kinds whose lead names a pipeline stage, read from `event.title`. */
const NAMES_A_STAGE: ReadonlySet<string> = new Set(['stage_completed']);

/** The raw kinds whose lead names a sub-agent, read from `event.title`. */
const NAMES_A_SUBAGENT: ReadonlySet<string> = new Set([
  'subagent_dispatched',
  'subagent_returned',
]);

/**
 * `event`'s title, when it is a real name rather than the raw kind standing
 * in for one that was never given — or the declared-absent fallback word.
 *
 * `eventFromStream` falls `title` back to the raw kind itself when the
 * payload carried no `name` (`text(payload, 'name') === '' ? name : ...`).
 * That fallback is right for the transcript's own meta line, which already
 * shows the raw kind beside the kind label — but a narration template that
 * printed it as if it were a capability's name would read "Called
 * tool_called", so the same signal that produced the fallback is what tells
 * this function to reach for the honest word instead.
 */
function namedOrFallback(event: TranscriptEvent, locale: Locale): string {
  const real = event.title !== '' && event.title !== event.rawKind;
  if (real) return event.title;
  if (NAMES_A_SUBAGENT.has(event.rawKind))
    return message(locale, 'transcript.narration.unnamedSubagent');
  if (NAMES_A_STAGE.has(event.rawKind))
    return message(locale, 'transcript.narration.unnamedStage');
  return message(locale, 'transcript.narration.unnamedCapability');
}

/**
 * `event`, as one sentence in the viewer's language.
 *
 * The single point every reader of a transcript passes through to get from
 * "an event happened" to "a sentence about it" — called from the view for
 * both a replayed run and a live one, over the same `TranscriptEvent[]`
 * `eventsFromReplay` and `eventsFromStream`/`eventFromStream` already
 * produce. A pure function of the event's own fields is what makes "replay
 * and stream narrate identically" a property of the code rather than a
 * promise: two events with the same `rawKind`, `title` and `detail` narrate
 * to the same string regardless of which reader built them.
 *
 * A kind outside `NARRATION_LEAD` — one this build has never met — renders
 * the generic sentence naming the raw kind. Never JSON, never a blank line:
 * the floor every event has, known or not.
 */
export function narrate(event: TranscriptEvent, locale: Locale): string {
  const key = NARRATION_LEAD[event.rawKind];
  const lead =
    key === undefined
      ? message(locale, 'transcript.narration.unknown', { kind: event.rawKind })
      : message(
          locale,
          key,
          NAMES_A_CAPABILITY.has(event.rawKind) ||
            NAMES_A_SUBAGENT.has(event.rawKind) ||
            NAMES_A_STAGE.has(event.rawKind)
            ? { name: namedOrFallback(event, locale) }
            : {},
        );
  return event.detail === '' ? lead : `${lead} — ${event.detail}`;
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
