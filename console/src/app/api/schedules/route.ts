import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * A scheduled investigation's five writes and its one preview, forwarded and
 * never decided here.
 *
 * One courier for six operations rather than six files, and the closed
 * table below is what keeps that from becoming an open proxy: an operation
 * this handler does not name cannot be reached through it, and neither can a
 * path this handler does not build.
 *
 * `create` and `preview` need no identifier — the job id is in the body for
 * `create`, because it is the caller who names a schedule, not the
 * deployment; `preview` has no identifier because there is nothing saved yet
 * to name. Every other operation acts on a schedule that already exists, and
 * is refused without an identifier to act on.
 *
 * The list itself is read straight from the screen, server-side, with the
 * same credential this handler carries at the network edge — it needs no
 * courier of its own. Only an action triggered by something a person
 * presses, write or preview alike, has to cross from a client component that
 * cannot read an HTTP-only cookie.
 */

/** One field of an answer that crossed a process, or a stated fallback. */
function pick(record: unknown, name: string, fallback: unknown): unknown {
  const found: unknown = Reflect.get(Object(record), name);
  return found ?? fallback;
}

interface Forwarded {
  readonly method: 'POST' | 'PUT' | 'DELETE';
  /** Whether this operation acts on an existing schedule and needs its id. */
  readonly needsId: boolean;
  readonly path: (jobId: string) => string;
}

/** Every operation this courier will forward, and where each goes. */
const OPERATIONS: Readonly<Record<string, Forwarded>> = {
  create: { method: 'POST', needsId: false, path: () => '' },
  update: { method: 'PUT', needsId: true, path: (jobId) => `/${jobId}` },
  delete: { method: 'DELETE', needsId: true, path: (jobId) => `/${jobId}` },
  enable: { method: 'POST', needsId: true, path: (jobId) => `/${jobId}/enable` },
  disable: { method: 'POST', needsId: true, path: (jobId) => `/${jobId}/disable` },
  // Needs no id, the same way `create` does not: a preview is of a cron
  // expression nobody has saved yet, so there is nothing for an id to name.
  preview: { method: 'POST', needsId: false, path: () => '/preview' },
};

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const jobId = String(Reflect.get(Object(body), 'jobId') ?? '');
  const operation = String(Reflect.get(Object(body), 'operation') ?? '');
  const payload: unknown = Reflect.get(Object(body), 'payload');
  const forwarded = OPERATIONS[operation];
  if (forwarded === undefined || (forwarded.needsId && jobId === '')) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/schedules${forwarded.path(encodeURIComponent(jobId))}`;
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
    // The gateway's own words on a refusal, nested under `error` the way
    // every handler in `gateway/http/errors.py` shapes one — including a cron
    // expression the deployment would not accept, crossed back exactly as it
    // was worded rather than replaced with a sentence this process invented.
    const problem = pick(Object(pick(answered, 'error', {})), 'message', '');
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        reason: typeof problem === 'string' ? problem : '',
        answer: answered,
      },
      { status: answer.status },
    );
  } catch {
    // The deployment, not this process. Saying "refused" would send somebody
    // to look at the wrong machine, and they would find nothing wrong with it.
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
