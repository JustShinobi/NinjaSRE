import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * A run's event stream, forwarded byte for byte.
 *
 * It exists for the reason every other handler under `src/app/api/` exists: the
 * credential is in an HTTP-only cookie, so a browser cannot present it to the
 * deployment. This is a courier — it adds the bearer token, turns the `cursor`
 * query into the `Last-Event-ID` header the deployment reads, and pipes the
 * body through untouched.
 *
 * **It rewrites nothing.** The frames the browser reads are the frames the
 * gateway wrote, including the `id` on each one, because the cursor arithmetic
 * belongs to the client and a courier that re-numbered events would be a second
 * opinion about what order a run happened in.
 *
 * The refusal statuses pass through as statuses rather than as an error frame,
 * which is what lets a session that expired mid-stream end the session instead
 * of being retried as if it were a network fault.
 */

/** Node rather than the edge runtime: this holds a socket open for minutes. */
export const runtime = 'nodejs';

/** Never cached, never pre-rendered. A cached stream is a recording. */
export const dynamic = 'force-dynamic';

export async function GET(
  request: NextRequest,
  { params }: { readonly params: Promise<{ readonly runId: string }> },
): Promise<Response> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ streaming: false }, { status: 401 });
  }

  const { runId } = await params;
  const cursor = request.nextUrl.searchParams.get('cursor') ?? '';
  const headers: Record<string, string> = {
    authorization: `Bearer ${credential}`,
    accept: 'text/event-stream',
  };
  // Absent on a first connection, because "everything after nothing" and
  // "everything" are the same request and the deployment spells the second one
  // by receiving no header at all.
  if (cursor !== '') headers['last-event-id'] = cursor;

  const address = `${apiOrigin()}/v1/investigations/${encodeURIComponent(runId)}/stream`;
  try {
    const answer = await fetch(address, {
      headers,
      cache: 'no-store',
      signal: request.signal,
    });
    if (!answer.ok || answer.body === null) {
      return NextResponse.json({ streaming: false }, { status: answer.status });
    }
    return new Response(answer.body, {
      status: 200,
      headers: {
        'content-type': 'text/event-stream',
        'cache-control': 'no-cache, no-transform',
        // Named for the proxies that buffer a response until it is complete,
        // which for a stream is until the run ends.
        'x-accel-buffering': 'no',
      },
    });
  } catch {
    // A deployment that cannot be reached is not a refused stream, and the
    // difference decides whether the console retries or says it has given up.
    return NextResponse.json({ streaming: false, reachable: false }, { status: 502 });
  }
}
