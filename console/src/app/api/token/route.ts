import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Issuing and revoking a machine token, forwarded once.
 *
 * The sibling of `../delivery-token/`, which mints one credential for one
 * purpose and refuses to ask for anything wider. This one is the general
 * surface, and the difference in what it is allowed to do is deliberate: the
 * *gateway* decides which scopes an operator may issue, because it is the only
 * thing that knows what that operator already holds. A ceiling enforced here
 * would be a second opinion about permissions, held by the process least
 * qualified to have one.
 *
 * The secret crosses this process once, inside one response body, and is never
 * assigned anywhere that outlives the call — no cache, no cookie, no log line.
 * There is no route that reads it back, here or on the deployment: the store
 * holds a hash, so a page reload is a page with nothing on it.
 */

/** Issue a token and return its secret, once. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const name = String(Reflect.get(Object(body), 'name') ?? '').trim();
  if (name === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }
  const permissions: unknown = Reflect.get(Object(body), 'permissions');
  const lifetime: unknown = Reflect.get(Object(body), 'lifetimeDays');

  try {
    const answer = await fetch(`${apiOrigin()}/identity/tokens`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({
        name,
        permissions: Array.isArray(permissions) ? permissions.map(String) : [],
        ...(typeof lifetime === 'number' ? { lifetime_days: lifetime } : {}),
      }),
      cache: 'no-store',
    });
    const issued: unknown = await answer.json().catch(() => ({}));
    const secret: unknown = Reflect.get(Object(issued), 'secret');
    const detail: unknown = Reflect.get(Object(issued), 'detail');
    const superseded: unknown = Reflect.get(Object(issued), 'superseded');
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        reason: typeof detail === 'string' ? detail : '',
        secret: typeof secret === 'string' ? secret : '',
        // Which live tokens this issuance replaced, so a purpose that already
        // had one substitutes rather than accumulates beside it, declared and
        // visible rather than only discoverable afterwards in the audit trail.
        superseded: Array.isArray(superseded) ? superseded.map(String) : [],
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}

/** Revoke one token. Clients using it stop authenticating on the next request. */
export async function DELETE(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const tokenId = request.nextUrl.searchParams.get('token_id') ?? '';
  if (tokenId === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  try {
    const answer = await fetch(
      `${apiOrigin()}/identity/tokens/${encodeURIComponent(tokenId)}`,
      {
        method: 'DELETE',
        headers: {
          authorization: `Bearer ${credential}`,
          accept: 'application/json',
        },
        cache: 'no-store',
      },
    );
    const revoked: unknown = await answer.json().catch(() => ({}));
    const detail: unknown = Reflect.get(Object(revoked), 'detail');
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        reason: typeof detail === 'string' ? detail : '',
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
