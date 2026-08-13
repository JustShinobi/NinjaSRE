/**
 * What a row in `/identity/tokens` *is*, told apart without a browser.
 *
 * Its own module, with no `'use client'`, for the reason `stoppage.ts` and
 * `first-run/tutorial-setting.ts` exist: both sides need it. The Administration
 * screen is resolved on the server and splits the list before it renders; the
 * token panels are client components. A predicate that lived with the panels
 * could not be called from the screen at all — Next refuses to invoke a client
 * export from the server, and the refusal arrives as the whole route throwing
 * rather than as a component misbehaving.
 *
 * This console has now paid for that boundary three times. The rule it settled
 * on: a pure function two sides need lives in a module with no directive, and
 * the components import it — never the other way round, and never through a
 * re-export from the client module, which is still a client boundary.
 */

/** One token as `/identity/tokens` reports it, whichever kind of token it is. */
export interface IssuedToken {
  readonly tokenId: string;
  readonly name: string;
  readonly scopes: readonly string[];
  readonly revoked: boolean;
  readonly expires: string;
}

/**
 * The exact name the platform's local accounts issue a sign-in token under.
 *
 * Matched by value: the console has no import path to the platform's own
 * constant, and this is the one thing that has to stay a literal string.
 */
export const CONSOLE_SESSION_NAME = 'Console sign-in';

/** Whether `token` is a browser sign-in rather than a credential somebody minted. */
export function isConsoleSession(token: Pick<IssuedToken, 'name'>): boolean {
  return token.name === CONSOLE_SESSION_NAME;
}
