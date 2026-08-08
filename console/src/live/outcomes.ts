import type { SemanticRole } from '@/design/tokens';

/**
 * What a background action did, announced — and written down somewhere else.
 *
 * **A toast is never the only record.** Toasts are dismissible, they are easy to
 * miss, and they are gone by the time somebody comes back from the kitchen. An
 * operator who missed one still has to be able to find out what happened, so
 * every outcome names where the same thing is durably recorded: the run's
 * transcript, the audit view, or the notification centre.
 *
 * That is enforced by the type rather than by a reviewer noticing —
 * `recordedAt` is required and `announce` refuses a blank one. There is no way
 * to spell an outcome that exists only as a toast.
 */

/** One thing that happened, and where it is written down. */
export interface Outcome {
  /** Stable, so the same outcome announced twice does not stack. */
  readonly id: string;
  readonly role: SemanticRole;
  readonly message: string;
  /** The durable record. Required: a toast is never the only one. */
  readonly recordedAt: { readonly href: string; readonly label: string };
}

/**
 * How many are shown at once.
 *
 * A stack that grows without bound is a stack that covers the screen it is
 * reporting on; the ones pushed out are still in their durable record, which is
 * the whole point of there being one.
 */
export const OUTCOME_LIMIT = 3;

/**
 * `outcomes` with `outcome` announced.
 *
 * Throws on an outcome with nowhere durable behind it. A thrown error in
 * development is how this rule stays true; a silent acceptance is how a toast
 * quietly becomes the only record of a failed remediation.
 */
export function announce(
  outcomes: readonly Outcome[],
  outcome: Outcome,
): readonly Outcome[] {
  if (outcome.recordedAt.href.trim() === '' || outcome.recordedAt.label.trim() === '') {
    throw new Error(
      `the outcome ${outcome.id} names no durable record; a toast is never the only one`,
    );
  }
  const without = outcomes.filter((held) => held.id !== outcome.id);
  return [...without, outcome].slice(-OUTCOME_LIMIT);
}

/** `outcomes` without the one `id` names. */
export function dismiss(outcomes: readonly Outcome[], id: string): readonly Outcome[] {
  return outcomes.filter((outcome) => outcome.id !== id);
}
