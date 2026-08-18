import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Creating a person with a local password, forwarded once.
 *
 * The sibling of `../grants/`: a write this browser cannot make directly,
 * because the credential it would need lives in an HTTP-only cookie no
 * component can read. `POST /identity/principals` decides everything about
 * whether the write is allowed and what it is refused for — a caller without
 * `identity.write` never reaches this route's own body at all, because the
 * gateway's route table refuses the forwarded request before this file's
 * fetch ever returns — so nothing here re-checks a permission or re-derives
 * a refusal; it only carries the deployment's own answer back.
 *
 * `/identity/principals` answers a refusal the same shape `/identity/grants`
 * already does — `{"error": {"type", "message", "correlation_id"}}` — so
 * `reasonOf` reads it the same way, and the deployment's own sentence (a
 * duplicate email, most often) reaches the form verbatim.
 *
 * The password crosses this process once, in one request body, and is never
 * assigned anywhere that outlives the call — no cache, no cookie, no log
 * line. The gateway's own answer never carries one back: `UserView` has no
 * password field to begin with.
 */

/** The message a refusal carries, in the `{"error": {...}}` shape this route answers. */
function reasonOf(body: unknown): string {
  const error: unknown = Reflect.get(Object(body), 'error');
  const found: unknown = Reflect.get(Object(error), 'message');
  return typeof found === 'string' ? found : '';
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const email = String(Reflect.get(Object(body), 'email') ?? '');
  const displayName = String(Reflect.get(Object(body), 'display_name') ?? '');
  const password = String(Reflect.get(Object(body), 'password') ?? '');
  if (email === '' || displayName === '' || password === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  try {
    const answer = await fetch(`${apiOrigin()}/identity/principals`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({ email, display_name: displayName, password }),
      cache: 'no-store',
    });
    const answered: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        reason: reasonOf(answered),
        answer: answered,
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
