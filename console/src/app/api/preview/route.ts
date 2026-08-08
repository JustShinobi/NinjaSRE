import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * What saving a patch would resolve to — asked of the deployment, never worked
 * out here.
 *
 * The whole value of a configuration preview is that it is the *server's*
 * answer. A client-side merge that agrees with the server today is a client-side
 * merge that disagrees with it after the next change to inheritance, and the
 * disagreement surfaces as an operator who previewed one thing and saved
 * another. So this handler forwards the patch and returns the response body
 * verbatim: it has no merge in it, and there is nowhere else in the console that
 * one could be.
 *
 * It exists at all because the credential lives in an HTTP-only cookie, so a
 * browser cannot present it. This is a courier.
 */

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({}, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const nodeId = String(Reflect.get(Object(body), 'nodeId') ?? '');
  const patch: unknown = Reflect.get(Object(body), 'patch');
  if (nodeId === '' || typeof patch !== 'object' || patch === null) {
    return NextResponse.json({}, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/config/${encodeURIComponent(nodeId)}/preview`;
  try {
    const answer = await fetch(address, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({ patch }),
      cache: 'no-store',
    });
    const previewed: unknown = await answer.json().catch(() => ({}));
    // Verbatim. Reshaping it here would be the second opinion this handler
    // exists to avoid.
    return NextResponse.json(previewed, { status: answer.status });
  } catch {
    return NextResponse.json({ reachable: false }, { status: 502 });
  }
}
