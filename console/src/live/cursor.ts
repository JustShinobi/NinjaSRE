/**
 * Where this browser has got to in one run's stream.
 *
 * One integer and a run identifier, and both halves matter. Sequences restart
 * per run — which is what stops two busy investigations contending on one
 * counter — so an integer alone is ambiguous, and a client presenting a position
 * from a different run would silently be served the wrong backlog.
 *
 * The wire form is the deployment's: `run-id:position`, the same string the
 * gateway puts in an SSE frame's `id` and reads back out of `Last-Event-ID`.
 * `tests/contract/console/test_console_live.py` holds the separator against the
 * Python that writes it, because two spellings of one cursor is a reconnection
 * that starts the transcript again from the beginning and looks like it worked.
 */

/** Separates the run from the position. Neither half may contain it. */
export const CURSOR_SEPARATOR = ':';

/** The position of a client that has seen nothing of a run. */
export const NOTHING_SEEN = -1;

/**
 * The cursor a client at `position` presents for `runId`.
 *
 * Empty when nothing has been seen, because "everything after position -1" and
 * "everything" are the same request and the gateway spells the second one by
 * sending no `Last-Event-ID` at all.
 */
export function cursorOf(runId: string, position: number): string {
  if (runId === '' || position < 0) return '';
  return `${runId}${CURSOR_SEPARATOR}${String(position)}`;
}

/**
 * The position `cursor` encodes for `runId`, or `NOTHING_SEEN`.
 *
 * A cursor naming another run reads as nothing seen rather than as its own
 * number: taking the integer would resume this run from a position that means
 * something in a different one, which is a gap nobody would ever see reported.
 */
export function positionIn(cursor: string, runId: string): number {
  const at = cursor.lastIndexOf(CURSOR_SEPARATOR);
  if (at <= 0) return NOTHING_SEEN;
  if (cursor.slice(0, at) !== runId) return NOTHING_SEEN;
  const position = Number(cursor.slice(at + 1));
  if (!Number.isInteger(position) || position < 0) return NOTHING_SEEN;
  return position;
}
