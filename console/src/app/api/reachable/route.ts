import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The cheapest question this console can ask the deployment.
 *
 * A courier like every other route under `src/app/api/`, and here for the same
 * reason: the session credential is an HTTP-only cookie the browser cannot
 * read, so a request the browser makes straight at the gateway arrives
 * unauthenticated wherever the two are different hosts.
 *
 * It exists because the screen keeps itself current on a timer and has to be
 * able to say when that has stopped working. `router.refresh()` returns
 * nothing and reports nothing — it cannot fail in a way a component can see —
 * so the freshness indicator would otherwise be claiming the view was current
 * on the strength of having *attempted* to make it so. Saying "live" over
 * stale data is the one thing that indicator must never do, so the attempt is
 * paired with a hop that can actually fail, over the same path and the same
 * credential the refresh itself travels.
 *
 * `/health/ready` is the gateway's own readiness, which is the right question:
 * a deployment answering it is one whose reads will answer too, and one that
 * is not is exactly the case where the page on screen is quietly ageing.
 *
 * Nothing about the deployment's answer is forwarded. This route reports
 * whether the hop worked and nothing else — a readiness document contains
 * component names and failure reasons, and none of that belongs in a response
 * a timer fetches every fifteen seconds.
 */

/** Report whether the gateway answered, and nothing further. */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    // Not reachable-or-not: the session is gone, and the session controller is
    // what handles that. Answering 401 lets it, rather than having the
    // freshness indicator quietly count an expired session as an outage.
    return NextResponse.json({ reachable: false }, { status: 401 });
  }

  try {
    const answer = await fetch(`${apiOrigin()}/health/ready`, {
      headers: { authorization: `Bearer ${credential}` },
      cache: 'no-store',
    });
    return NextResponse.json(
      { reachable: answer.ok },
      { status: answer.ok ? 200 : 503 },
    );
  } catch {
    return NextResponse.json({ reachable: false }, { status: 503 });
  }
}
