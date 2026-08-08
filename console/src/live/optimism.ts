/**
 * A write the operator made, applied before the deployment has agreed to it.
 *
 * Optimism without a snapshot is worse than no optimism at all: a refused write
 * leaves the screen asserting something false, and the operator walks away
 * believing they approved a change that was rejected. So every attempt records
 * exactly what it replaced, and a refusal puts that back **and states the
 * deployment's reason** — not "that did not work", which tells nobody whether
 * to try again.
 *
 * Pure, and outside React, for the same reason the reducer is: this is the
 * behaviour a rollback test has to be able to drive without a browser.
 */

/** Where a write has got to. */
export const WRITE_STATES = ['resting', 'pending', 'applied', 'reverted'] as const;

export type WriteState = (typeof WRITE_STATES)[number];

/** One value being changed, and what it was before. */
export interface Write<T> {
  readonly state: WriteState;
  readonly value: T;
  /** What to put back. Present exactly while a write is in flight or reverted. */
  readonly snapshot: T | null;
  /** Why it was put back, in the deployment's own words. Empty until it is. */
  readonly reason: string;
}

/** A value nobody is changing. */
export function resting<T>(value: T): Write<T> {
  return { state: 'resting', value, snapshot: null, reason: '' };
}

/**
 * `next`, on screen immediately, with the old value kept.
 *
 * A second attempt while one is in flight keeps the *original* snapshot rather
 * than the intermediate one. Rolling back to a value that was itself never
 * confirmed would put a fiction on the screen in place of a falsehood.
 */
export function attempt<T>(write: Write<T>, next: T): Write<T> {
  return {
    state: 'pending',
    value: next,
    snapshot: write.snapshot ?? write.value,
    reason: '',
  };
}

/** The deployment agreed. The snapshot is dropped; there is nothing to go back to. */
export function confirmed<T>(write: Write<T>): Write<T> {
  return { state: 'applied', value: write.value, snapshot: null, reason: '' };
}

/**
 * The deployment refused. The old value goes back, with the reason beside it.
 *
 * A refusal with no reason still reverts, and says so — an unexplained
 * reversion is confusing, and leaving the false value on screen is worse.
 */
export function refused<T>(write: Write<T>, reason: string): Write<T> {
  return {
    state: 'reverted',
    value: write.snapshot ?? write.value,
    snapshot: null,
    reason,
  };
}

/**
 * The event carrying this change arrived, so the stream's version wins.
 *
 * This is what stops optimism and streaming double-applying: the optimistic
 * value is a stand-in for an event that has not arrived yet, and when it does
 * the stand-in is replaced rather than added to.
 */
export function superseded<T>(_write: Write<T>, value: T): Write<T> {
  return { state: 'applied', value, snapshot: null, reason: '' };
}

/** Whether the screen is currently showing something unconfirmed. */
export function isPending<T>(write: Write<T>): boolean {
  return write.state === 'pending';
}
