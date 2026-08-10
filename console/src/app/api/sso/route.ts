import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The identity provider's three writes, forwarded and never decided here.
 *
 * A courier, like every route under `src/app/api/`. The closed table below is
 * what keeps one file for three operations from becoming an open proxy.
 *
 * Nothing about the ordering is enforced here, and deliberately: whether a test
 * has passed against *these* settings is the deployment's answer, derived from
 * the settings themselves. A console that tracked it would be a second answer,
 * and the day the two disagreed somebody would activate a provider nobody had
 * tested — which is the failure this whole flow exists to prevent.
 */

/** Every operation this courier will forward, and where each goes. */
const OPERATIONS: Readonly<Record<string, { path: string; method: 'POST' | 'PUT' }>> = {
  save: { path: '', method: 'PUT' },
  test: { path: '/test', method: 'POST' },
  activate: { path: '/activate', method: 'POST' },
};

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

  try {
    const answer = await fetch(`${apiOrigin()}/identity/sso${forwarded.path}`, {
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
    const detail: unknown = Reflect.get(Object(answered), 'detail');
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        reason: typeof detail === 'string' ? detail : '',
        answer: answered,
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
