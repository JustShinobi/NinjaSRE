/**
 * Authentication, checked above the router.
 *
 * This is the property the first console got right and the one a file-based
 * router loses most easily: with a page per file, the natural place to check
 * whether somebody is signed in is inside each page, and then a page added in a
 * hurry is a page that is not checked. Nothing here is per page. One decision
 * runs before routing, over every path, and a route added tomorrow is guarded by
 * having been added.
 *
 * The decision is a pure function so that it can be enumerated: the suite walks
 * the route manifest and asserts each area redirects, which means a new area is
 * covered by the test that already exists rather than by one somebody remembers
 * to write.
 */

import { SESSION_COOKIE, SESSION_ENDPOINT, signInHref, SIGN_IN_PATH } from './cookies';

/**
 * The header the middleware forwards the current path in.
 *
 * A server layout is not told which route rendered it. The shell has to mark
 * exactly one navigation entry as current, and reading the path from a client
 * hook instead would mean the mark arrives after hydration — which is one frame
 * of a sidebar with nothing current, on every navigation.
 */
export const CURRENT_PATH_HEADER = 'x-current-path';

/** What the guard decided about one request. */
export type GuardDecision =
  { readonly kind: 'allow' } | { readonly kind: 'redirect'; readonly to: string };

/**
 * The paths that are reachable without a session, and the whole of that list.
 *
 * The sign-in itself, and the route handler it posts to. Nothing else — not the
 * gallery, not an asset route, not a health check. A path exempted for
 * convenience is the one an unauthenticated visitor uses to learn that this
 * deployment exists and what it is called.
 */
const EXEMPT: readonly string[] = [SIGN_IN_PATH, SESSION_ENDPOINT];

function isExempt(pathname: string): boolean {
  return EXEMPT.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

/**
 * Whether this request may proceed, and where it goes instead.
 *
 * `cookies` is whatever the request carried, keyed by name. The guard asks only
 * whether the session cookie is present — validating it is the API's job, and a
 * console that decided a token was good would be a console holding a second
 * opinion about authentication.
 */
export function guard(
  pathname: string,
  search: string,
  cookies: ReadonlyMap<string, string>,
): GuardDecision {
  if (isExempt(pathname)) {
    return { kind: 'allow' };
  }
  const session = cookies.get(SESSION_COOKIE);
  if (session !== undefined && session !== '') {
    return { kind: 'allow' };
  }
  return { kind: 'redirect', to: signInHref(`${pathname}${search}`) };
}
