/**
 * One event off the wire, and what a frame the console cannot read costs.
 *
 * A malformed frame is skipped rather than thrown on. An unreadable event
 * during an incident should cost the reader one line of the transcript, not the
 * rest of the stream — the same disposition the deployment's own reader takes,
 * for the same reason.
 *
 * Nothing here interprets a payload. It is carried through as `unknown` and the
 * transcript decides what a kind means, so this module cannot become a second
 * opinion about what the deployment sends.
 */

/** One event of a run, as the stream spells it. */
export interface StreamEvent {
  readonly runId: string;
  readonly kind: string;
  readonly sequence: number;
  /** ISO 8601, or empty when the deployment recorded no instant. */
  readonly occurredAt: string;
  readonly turnId: string;
  readonly payload: unknown;
}

function field(record: unknown, name: string): unknown {
  return Reflect.get(Object(record), name);
}

function text(record: unknown, name: string): string {
  const found = field(record, name);
  return typeof found === 'string' ? found : '';
}

/**
 * The event `document` describes, or `null` when it does not describe one.
 *
 * A run and an integer sequence are the two fields nothing works without: the
 * run because a cursor is ambiguous without it, and the sequence because it is
 * what makes a duplicate detectable. Anything else missing is a thinner event
 * rather than an unusable one.
 */
export function eventFrom(document: unknown): StreamEvent | null {
  const runId = text(document, 'run_id');
  const sequence = field(document, 'sequence');
  if (runId === '' || typeof sequence !== 'number' || !Number.isInteger(sequence)) {
    return null;
  }
  return {
    runId,
    kind: text(document, 'kind'),
    sequence,
    occurredAt: text(document, 'occurred_at'),
    turnId: text(document, 'turn_id'),
    payload: field(document, 'payload') ?? {},
  };
}

/**
 * The event an SSE frame's `data` carries, or `null`.
 *
 * A comment frame and an empty one both arrive here as an empty string, and
 * both are events this console has nothing to do with rather than faults.
 */
export function eventFromFrame(data: string): StreamEvent | null {
  if (data === '') return null;
  try {
    return eventFrom(JSON.parse(data));
  } catch {
    return null;
  }
}
