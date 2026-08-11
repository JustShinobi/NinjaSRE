import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The autonomy policy's writes, forwarded and never decided here.
 *
 * One courier for several operations rather than one file each, and the closed
 * table below is what keeps that from becoming an open proxy: an operation this
 * handler does not name cannot be reached through it, so the console's own
 * process can never be used to address an arbitrary path on the deployment.
 *
 * `revoke-override` is the one entry that is not a plain `POST`/`PUT` at a fixed
 * path: revoking is `DELETE .../overrides/{name}`, so its path carries a
 * segment read from the payload at request time rather than a literal — still
 * one row in a closed table, never a path a caller builds.
 *
 * Nothing is computed. What a policy change would decide differently is
 * `preview`'s answer and what one action would resolve to is `explain`'s, both
 * from the deployment — because a console that worked either out for itself
 * would be a second implementation of resolution, and the day it drifted an
 * operator would raise autonomy on the strength of a sentence this process
 * wrote. A refused override — including one this node never granted — is
 * reported back exactly as the deployment worded it, for the same reason.
 */

interface Forwarded {
  readonly path: string;
  readonly method: 'POST' | 'PUT' | 'DELETE';
  /** Whether the address carries `payload.name` as its last, encoded segment. */
  readonly named?: true;
}

/** Every operation this courier will forward, and where each goes. */
const OPERATIONS: Readonly<Record<string, Forwarded>> = {
  save: { path: '', method: 'PUT' },
  preview: { path: '/preview', method: 'POST' },
  explain: { path: '/explain', method: 'POST' },
  'dry-run': { path: '/dry-run', method: 'POST' },
  override: { path: '/overrides', method: 'POST' },
  'revoke-override': { path: '/overrides', method: 'DELETE', named: true },
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
  const name =
    forwarded?.named === true ? String(Reflect.get(Object(payload), 'name') ?? '') : '';
  if (
    nodeId === '' ||
    forwarded === undefined ||
    (forwarded.named === true && name === '')
  ) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const segment = forwarded.named === true ? `/${encodeURIComponent(name)}` : '';
  const address = `${apiOrigin()}/v1/autonomy/policy/${encodeURIComponent(nodeId)}${forwarded.path}${segment}`;
  try {
    const answer = await fetch(address, {
      method: forwarded.method,
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      // A `DELETE` here carries no body: the name is already in the address,
      // and a body on a request the deployment does not read is noise.
      ...(forwarded.method === 'DELETE' ? {} : { body: JSON.stringify(payload ?? {}) }),
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
