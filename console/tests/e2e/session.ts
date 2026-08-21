import type { BrowserContext } from '@playwright/test';

/**
 * A signed-in browser.
 *
 * Every route is guarded above the router, so a browser with no session sees the
 * sign-in and nothing else — which is the property the suite is glad of and the
 * reason every test that is *not* about signing in has to establish one first.
 *
 * The cookie is set directly rather than by driving the form. Driving the form
 * would make every test depend on the sign-in working, so a change there would
 * fail forty tests instead of the one that is about it; `signing-in.spec.ts` is
 * the one that drives it.
 */

/** The credential the mock data plane accepts, which is any credential. */
export const CREDENTIAL = 'tok_e2e';

/** Give `context` a session, so the guard lets it through. */
export async function signIn(context: BrowserContext, baseURL: string): Promise<void> {
  const url = new URL(baseURL);
  const ending = new Date(Date.now() + 3600_000).toISOString();
  await context.addCookies([
    {
      name: 'ninjasre_session',
      value: CREDENTIAL,
      domain: url.hostname,
      path: '/',
      httpOnly: true,
      sameSite: 'Strict',
    },
    {
      name: 'ninjasre_session_expires',
      value: ending,
      domain: url.hostname,
      path: '/',
      sameSite: 'Strict',
    },
  ]);
}
