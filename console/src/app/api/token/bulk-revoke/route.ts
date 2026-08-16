import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Revoking a set of machine tokens at once, forwarded once.
 *
 * The sibling of `../route.ts`'s single-token `DELETE`: this one exists for
 * "revoke all but the newest token issued for this purpose", the one gesture
 * `settings/machine-tokens.tsx` offers over a group. Selection is by explicit
 * id — the *console* already knows which ids are older, from the same list it
 * rendered — so this forwards a set rather than deciding one on the gateway's
 * behalf.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const tokenIds: unknown = Reflect.get(Object(body), 'token_ids');
  const reason = String(Reflect.get(Object(body), 'reason') ?? '');
  const ids = Array.isArray(tokenIds) ? tokenIds.map(String) : [];
  if (ids.length === 0) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  try {
    const answer = await fetch(`${apiOrigin()}/identity/tokens/revoke`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({
        token_ids: ids,
        ...(reason === '' ? {} : { reason }),
      }),
      cache: 'no-store',
    });
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
