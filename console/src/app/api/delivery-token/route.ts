import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * A delivery token on its way out, and the one thing this handler does with it.
 *
 * It forwards it. The secret is created by the deployment, crosses this process
 * once inside one response body, and is never assigned anywhere that outlives
 * the call — no cache, no cookie, no log line. This is the same courier
 * `src/app/api/credential/` is for a credential travelling the other way, and
 * it exists for the same reason: the session credential is an HTTP-only,
 * `SameSite=Strict` cookie on the console's own host, so a request the browser
 * makes straight at the gateway arrives unauthenticated wherever the two are
 * different hosts.
 *
 * **The scope is not taken from the browser.** It is the permission the
 * deployment itself named on `/v1/ingress/sources`, sent back here — but a
 * request naming a wider one would be a request to mint a wider credential, so
 * anything but the delivery permission is refused before it leaves this
 * process. The gateway would refuse to exceed the owner's own permissions
 * anyway; this refuses to *ask*, which is the difference between a boundary and
 * a hope.
 */

/** The only scope this endpoint will ever ask for. */
const DELIVERY_PERMISSION = 'webhook.deliver';

/** How long a delivery credential lives before it has to be re-issued. */
const LIFETIME_DAYS = 365;

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const permission: unknown = Reflect.get(Object(body), 'permission');
  if (permission !== DELIVERY_PERMISSION) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  try {
    const answer = await fetch(`${apiOrigin()}/identity/tokens`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({
        name: 'alert-delivery',
        permissions: [DELIVERY_PERMISSION],
        lifetime_days: LIFETIME_DAYS,
      }),
      cache: 'no-store',
    });
    const issued: unknown = await answer.json().catch(() => ({}));
    const secret: unknown = Reflect.get(Object(issued), 'secret');
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        secret: typeof secret === 'string' ? secret : '',
      },
      { status: answer.status },
    );
  } catch {
    // The deployment, not this process. Saying "refused" would send somebody to
    // look at the wrong machine, and they would find nothing wrong with it.
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
