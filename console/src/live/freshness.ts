/**
 * Whether what is on screen is current, and what the frame says about it.
 *
 * The complaint this answers is that an operator had to press reload to find
 * out whether anything had moved — on a console whose whole subject is a
 * deployment that changes while nobody is looking. A screen showing changing
 * data has to say whether it is current, and then it has to actually stay
 * current without being asked.
 *
 * **This is a re-read, not a stream, and the vocabulary here says so.** The
 * run-detail view has a real event stream because a run emits events with a
 * sequence a client can replay from. Nothing equivalent exists for the estate:
 * the event broker keys every subscription by run identifier, a run event
 * carries no tenant field, the cursor type refuses an empty run identifier and
 * there is no cross-run ordered query — so a session-wide stream is a piece of
 * infrastructure with a migration and an authorisation review, not a topic
 * string. Until that exists, the honest thing is to re-read on a timer and to
 * be exact about it, rather than to draw a chip that implies a socket.
 *
 * What that buys is still the whole of the complaint: a refresh is a segment
 * fetch rather than a document load, so the frame is not rebuilt, the scroll
 * position survives, and nobody presses anything.
 */

/** How often the view re-reads while the tab is being looked at, in ms. */
export const REFRESH_INTERVAL_MS = 15_000;

/**
 * How long a failing re-read waits before the next attempt, in ms.
 *
 * Growing, and stopping at a minute: a gateway that has been unreachable for
 * four attempts is not going to be reached by asking faster, and a console
 * left open overnight against a deployment that is down should not spend the
 * night hammering it.
 */
export const REFRESH_BACKOFF_MS: readonly number[] = [15_000, 30_000, 60_000];

/**
 * How many consecutive failures before the view stops claiming to be current.
 *
 * One failure is a hiccup and the data on screen is still seconds old. Three is
 * a deployment the console cannot reach, and saying "live" over stale data is
 * the one thing this indicator must never do.
 */
export const STALE_AFTER_FAILURES = 3;

export const FRESHNESS_STATES = ['live', 'refreshing', 'stale', 'paused'] as const;

export type Freshness = (typeof FRESHNESS_STATES)[number];

/** What the view is doing right now. */
export interface FreshnessInput {
  /** Whether the tab is being looked at. A hidden tab is not re-read. */
  readonly visible: boolean;
  /** Whether a re-read is in flight. */
  readonly refreshing: boolean;
  /** How many re-reads have failed in a row. */
  readonly failures: number;
}

/**
 * The state to draw.
 *
 * Order matters and is deliberate. Hidden wins over everything: a tab nobody
 * is looking at is not being kept current and must not claim to be. Stale wins
 * over refreshing, because an attempt in flight after three failures is still
 * an attempt over data nobody should trust yet.
 */
export function freshnessOf({
  visible,
  refreshing,
  failures,
}: FreshnessInput): Freshness {
  if (!visible) return 'paused';
  if (failures >= STALE_AFTER_FAILURES) return 'stale';
  if (refreshing) return 'refreshing';
  return 'live';
}

/**
 * How long to wait before the next attempt, given how many have failed.
 *
 * Zero failures is the ordinary interval. Past the end of the backoff table
 * the last step repeats rather than growing without bound — an operator who
 * fixes the gateway should not have to wait a quarter of an hour for the
 * console to notice.
 */
export function delayAfter(failures: number): number {
  if (failures <= 0) return REFRESH_INTERVAL_MS;
  const step = Math.min(failures, REFRESH_BACKOFF_MS.length) - 1;
  return REFRESH_BACKOFF_MS[step] ?? REFRESH_INTERVAL_MS;
}
