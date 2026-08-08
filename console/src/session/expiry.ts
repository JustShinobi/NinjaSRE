/**
 * Saying the session is about to end, before it ends.
 *
 * The failure this replaces is specific: a token expires, the next eleven
 * requests are refused, and the operator finds out through a wall of errors on
 * the screen they were reading. Warning afterwards is not warning.
 *
 * The boundary is the thing to test, not the aftermath. At exactly the warning
 * threshold the console is already warning; one second earlier it is not.
 */

import { SESSION_WARNING_SECONDS } from './cookies';

/** Where a session is in its life. */
export type SessionPhase = 'valid' | 'expiring' | 'expired' | 'unknown';

export interface SessionLife {
  readonly phase: SessionPhase;
  /** Whole seconds until the end, floored at zero. */
  readonly secondsLeft: number;
}

/**
 * How long `expiresAt` has left at `now`, and what to do about it.
 *
 * An absent or unparseable expiry is `unknown` rather than `expired`. A console
 * that signed somebody out because it could not read a cookie would be a console
 * that signs people out when a proxy strips one, and the refusal that actually
 * matters arrives from the API as a 401 either way.
 */
export function sessionLife(
  expiresAt: string | Date | null | undefined,
  now: Date,
  warningSeconds: number = SESSION_WARNING_SECONDS,
): SessionLife {
  if (expiresAt === null || expiresAt === undefined || expiresAt === '') {
    return { phase: 'unknown', secondsLeft: 0 };
  }
  const end = expiresAt instanceof Date ? expiresAt : new Date(expiresAt);
  if (Number.isNaN(end.getTime())) {
    return { phase: 'unknown', secondsLeft: 0 };
  }
  const secondsLeft = Math.max(0, Math.floor((end.getTime() - now.getTime()) / 1000));
  if (secondsLeft <= 0) {
    return { phase: 'expired', secondsLeft: 0 };
  }
  if (secondsLeft <= warningSeconds) {
    return { phase: 'expiring', secondsLeft };
  }
  return { phase: 'valid', secondsLeft };
}
