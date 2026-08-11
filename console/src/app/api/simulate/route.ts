import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * What today's rules would do with this payload — asked of the deployment.
 *
 * The same argument the configuration preview makes, and it is the one the
 * whole simulation rests on: the answer has to come from the function the live
 * ingress path runs. A matcher reimplemented in a browser would agree with the
 * server exactly until the day it did not, and the disagreement would surface
 * as an operator who simulated one thing and saved another.
 *
 * A courier and nothing else: the credential lives in an HTTP-only cookie, so a
 * browser cannot present it. The body goes out as it came in and the answer
 * comes back verbatim.
 */

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({}, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  if (typeof body !== 'object' || body === null) {
    return NextResponse.json({}, { status: 400 });
  }

  try {
    const answer = await fetch(`${apiOrigin()}/v1/transit/simulate`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify(body),
      cache: 'no-store',
    });
    const simulated: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(simulated, { status: answer.status });
  } catch {
    return NextResponse.json({ reachable: false }, { status: 502 });
  }
}
