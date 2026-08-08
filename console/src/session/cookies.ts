/**
 * The session, as it is kept in a browser — which is to say, not.
 *
 * The credential never reaches anything a component can read. The console
 * exchanges it for an HTTP-only, `SameSite=Strict` cookie in a route handler, so
 * there is no path from JavaScript in this application to the token, and
 * therefore no path from a bug in this application to leaking one. That is a
 * structural property rather than a discipline: `document.cookie` cannot see an
 * HTTP-only cookie however hard a component tries.
 *
 * A second cookie carries **only the instant the session ends**, and it is
 * deliberately readable. The expiry warning has to be rendered before the expiry
 * rather than after it, which means the client has to know when that is; an
 * instant is not a secret, and the alternative is a poll that discovers the
 * expiry by being refused.
 *
 * These names and durations are mirrored in `config/constants/console.py` and
 * held equal by `tests/contract/console/test_console_shell.py`, so changing one
 * without the other fails the gate rather than the deployment.
 */

/** The credential. HTTP-only, so nothing in a component can read it. */
export const SESSION_COOKIE = 'ninjasre_session';

/** When the session ends. Readable on purpose; it holds an instant, not a secret. */
export const SESSION_EXPIRY_COOKIE = 'ninjasre_session_expires';

/** How long a console session lasts before it has to be established again. */
export const SESSION_LIFETIME_SECONDS = 43200;

/** How long before the end the console says so. */
export const SESSION_WARNING_SECONDS = 300;

/** Where a viewer's chosen language is kept. Not a secret, so not HTTP-only. */
export const LOCALE_COOKIE = 'ninjasre_locale';

/** The route handler that establishes a session and the one that ends it. */
export const SESSION_ENDPOINT = '/api/session';

/** Where an unauthenticated visitor is sent, and the only page they are shown. */
export const SIGN_IN_PATH = '/sign-in';

/** The query parameter carrying the route to come back to. */
export const RETURN_TO_PARAM = 'from';

/** Why a session ended, which is what the sign-in page explains. */
export const SESSION_REASON_PARAM = 'reason';

/** The reasons a sign-in can be arrived at. */
export const SESSION_REASONS = ['expired', 'signed-out', 'none'] as const;

export type SessionReason = (typeof SESSION_REASONS)[number];

/** Whether `value` is a reason this console explains. */
export function isSessionReason(value: string | null): value is SessionReason {
  return value !== null && (SESSION_REASONS as readonly string[]).includes(value);
}

/**
 * Where to send somebody after they sign in.
 *
 * Only a path on this origin is accepted. A `returnTo` taken from a query
 * parameter is attacker-controlled by construction, and an open redirect on a
 * sign-in page is how a credential ends up being typed into somebody else's
 * console. `//evil.example` is rejected along with `https://evil.example`,
 * because the first is a scheme-relative URL and looks like a path.
 */
export function safeReturnTo(candidate: string | null | undefined): string {
  if (typeof candidate !== 'string' || candidate === '') {
    return '/';
  }
  if (!candidate.startsWith('/') || candidate.startsWith('//')) {
    return '/';
  }
  if (
    candidate.includes('\\') ||
    candidate.includes('\n') ||
    candidate.includes('\r')
  ) {
    return '/';
  }
  return candidate;
}

/** The sign-in address for a visitor who was trying to reach `returnTo`. */
export function signInHref(returnTo: string, reason: SessionReason = 'none'): string {
  const parameters = new URLSearchParams();
  const target = safeReturnTo(returnTo);
  if (target !== '/') {
    parameters.set(RETURN_TO_PARAM, target);
  }
  if (reason !== 'none') {
    parameters.set(SESSION_REASON_PARAM, reason);
  }
  const query = parameters.toString();
  return query === '' ? SIGN_IN_PATH : `${SIGN_IN_PATH}?${query}`;
}
