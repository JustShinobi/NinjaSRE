import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The operating context's two operations, forwarded and never decided here.
 *
 * One courier for both rather than two files, and the closed table below is what
 * keeps that from becoming an open proxy: an operation this handler does not
 * name cannot be reached through it, so the console's own process can never be
 * used to address an arbitrary path on the deployment.
 *
 * Nothing is assembled. The prompt a pending context would produce is
 * `preview`'s answer, from the deployment, because a console that joined the
 * shipped prompt to the sections itself would be a second implementation of the
 * assembly — and the day it drifted, somebody would approve a prompt nobody
 * sends.
 *
 * It exists at all because the credential lives in an HTTP-only cookie, so a
 * browser cannot present it. This is a courier.
 */

/** Every operation this courier will forward, and where each goes. */
const OPERATIONS: Readonly<Record<string, { path: string; method: 'POST' | 'PUT' }>> = {
  preview: { path: '/operating-context/preview', method: 'POST' },
  save: { path: '', method: 'PUT' },
};

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const nodeId = String(Reflect.get(Object(body), 'nodeId') ?? '');
  const operation = String(Reflect.get(Object(body), 'operation') ?? '');
  const payload: unknown = Reflect.get(Object(body), 'payload');
  const forwarded = OPERATIONS[operation];
  if (nodeId === '' || forwarded === undefined) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/config/${encodeURIComponent(nodeId)}${forwarded.path}`;
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
    const detail: unknown = Reflect.get(Object(answered), 'detail');
    // Verbatim under `answer`, with only the two facts this process knows
    // added: whether the deployment accepted it, and whether it replied at all.
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
