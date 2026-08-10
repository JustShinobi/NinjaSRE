import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The autonomy policy's four writes, forwarded and never decided here.
 *
 * One courier for four operations rather than four files, and the closed table
 * below is what keeps that from becoming an open proxy: an operation this
 * handler does not name cannot be reached through it, so the console's own
 * process can never be used to address an arbitrary path on the deployment.
 *
 * Nothing is computed. What a policy change would decide differently is
 * `preview`'s answer and what one action would resolve to is `explain`'s, both
 * from the deployment — because a console that worked either out for itself
 * would be a second implementation of resolution, and the day it drifted an
 * operator would raise autonomy on the strength of a sentence this process
 * wrote.
 */

/** Every operation this courier will forward, and where each goes. */
const OPERATIONS: Readonly<Record<string, { path: string; method: 'POST' | 'PUT' }>> = {
  save: { path: '', method: 'PUT' },
  preview: { path: '/preview', method: 'POST' },
  explain: { path: '/explain', method: 'POST' },
  'dry-run': { path: '/dry-run', method: 'POST' },
  override: { path: '/overrides', method: 'POST' },
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

  const address = `${apiOrigin()}/v1/autonomy/policy/${encodeURIComponent(nodeId)}${forwarded.path}`;
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
