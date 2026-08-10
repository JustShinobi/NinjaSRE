import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The emergency stop, forwarded.
 *
 * A courier like every other route under `src/app/api/`, and here for the same
 * reason: the session credential is an HTTP-only cookie the browser cannot
 * read, so a request the browser makes straight at the gateway arrives
 * unauthenticated wherever the two are different hosts.
 *
 * What is different about this one is what it must not do. It does not retry,
 * it does not queue, and it does not translate a refusal into a friendlier
 * status. The control exists for the ten seconds in which somebody has decided
 * that everything must stop, and the only two outcomes worth reporting are "the
 * deployment says it is stopped" and "the deployment did not say that".
 */

/** Stop every automated write, immediately. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const reason: unknown = Reflect.get(Object(body), 'reason');
  return forward(credential, 'POST', {
    reason: typeof reason === 'string' ? reason : '',
  });
}

/** Let automated writes happen again. */
export async function DELETE(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }
  return forward(credential, 'DELETE', null);
}

async function forward(
  credential: string,
  method: 'POST' | 'DELETE',
  body: unknown,
): Promise<NextResponse> {
  try {
    const answer = await fetch(`${apiOrigin()}/v1/autonomy/kill-switch`, {
      method,
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      ...(body === null ? {} : { body: JSON.stringify(body) }),
      cache: 'no-store',
    });
    const answered: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        engaged: Reflect.get(Object(answered), 'engaged') === true,
      },
      { status: answer.status },
    );
  } catch {
    // The deployment, not this process. An operator told that the stop was
    // refused would go looking for a permission; one told it could not be
    // reached goes and stops the thing by hand, which is the correct next move.
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
