import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Send a failed delivery again, because a person asked.
 *
 * A courier, like every other handler here: the credential is in an HTTP-only
 * cookie and a browser cannot present it. What it deliberately does *not* do is
 * decide whether the delivery is re-sendable — the gateway refuses one that did
 * not fail, and a check repeated here would be a second opinion that could
 * disagree with the first.
 */

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({}, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const deliveryId = String(Reflect.get(Object(body), 'deliveryId') ?? '');
  if (deliveryId === '') {
    return NextResponse.json({}, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/transit/deliveries/${encodeURIComponent(deliveryId)}/resend`;
  try {
    const answer = await fetch(address, {
      method: 'POST',
      headers: { authorization: `Bearer ${credential}`, accept: 'application/json' },
      cache: 'no-store',
    });
    const resent: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(resent, { status: answer.status });
  } catch {
    return NextResponse.json({ reachable: false }, { status: 502 });
  }
}
