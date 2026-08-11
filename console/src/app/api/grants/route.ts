import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Granting and removing a role, forwarded and never decided here.
 *
 * The closed table below is what keeps one file for two operations from
 * becoming an open proxy: an operation this handler does not name cannot be
 * reached through it. Neither is validated here — a role this deployment does
 * not have, or a removal that would leave the organisation with no owner, is
 * refused by the deployment itself, and this courier forwards that refusal
 * rather than deciding anything about it.
 *
 * `/identity/grants` answers a refusal as
 * `{"error": {"type", "message", "correlation_id"}}`, unlike the `detail`
 * shape the older writes under this directory forward — `reasonOf` reads that
 * shape specifically, so the deployment's own sentence reaches the form
 * verbatim rather than as `undefined`.
 */

const OPERATIONS: Readonly<Record<string, { method: 'POST' | 'DELETE' }>> = {
  add: { method: 'POST' },
  remove: { method: 'DELETE' },
};

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
  const operation = String(Reflect.get(Object(body), 'operation') ?? '');
  const payload: unknown = Reflect.get(Object(body), 'payload');
  const forwarded = OPERATIONS[operation];
  if (forwarded === undefined) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const grantId = String(Reflect.get(Object(payload), 'grant_id') ?? '');
  if (operation === 'remove' && grantId === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const address =
    operation === 'remove'
      ? `${apiOrigin()}/identity/grants/${encodeURIComponent(grantId)}`
      : `${apiOrigin()}/identity/grants`;

  try {
    const answer = await fetch(address, {
      method: forwarded.method,
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify(payload ?? {}),
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
