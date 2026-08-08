import { NextResponse, type NextRequest } from 'next/server';

import { CURRENT_PATH_HEADER, guard } from '@/session/guard';

/**
 * The one place authentication is checked.
 *
 * Next runs this before routing, over every request the matcher covers, which is
 * every request that is not a build artefact. There is deliberately no
 * per-page check anywhere in this application: a page that checked for itself
 * would be a page somebody could add without checking.
 *
 * The decision itself is in `src/session/guard.ts` so the suite can enumerate
 * the route manifest against it. This file is the adapter, and it is short on
 * purpose — an adapter with a branch in it is a second place the rule lives.
 */
export function middleware(request: NextRequest): NextResponse {
  const cookies = new Map(
    request.cookies.getAll().map((cookie) => [cookie.name, cookie.value] as const),
  );
  const decision = guard(request.nextUrl.pathname, request.nextUrl.search, cookies);
  if (decision.kind === 'allow') {
    // The path, forwarded to the layout. A server layout is not told which route
    // rendered it, and the shell has to mark exactly one navigation entry
    // current — reading it from `usePathname` instead would mean the mark
    // arrives after hydration, which is a frame of the wrong page.
    const forwarded = new Headers(request.headers);
    forwarded.set(
      CURRENT_PATH_HEADER,
      `${request.nextUrl.pathname}${request.nextUrl.search}`,
    );
    return NextResponse.next({ request: { headers: forwarded } });
  }
  return NextResponse.redirect(new URL(decision.to, request.nextUrl));
}

/**
 * Everything but Next's own build output.
 *
 * Written as an exclusion rather than as a list of pages, for the same reason
 * the guard is not per page: a list of pages is a list somebody forgets to
 * extend, and the thing they forget is the page nobody is watching.
 */
export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
