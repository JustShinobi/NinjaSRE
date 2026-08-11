import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * A detector's three writes, forwarded and never decided here.
 *
 * One courier for three operations rather than three files, and the closed
 * table below is what keeps that from becoming an open proxy: an operation
 * this handler does not name cannot be reached through it.
 *
 * **`dry-run` fires nothing.** It asks the deployment what a detector would
 * conclude against the signals already stored, and the deployment's own
 * answer says so (`fired: false`) rather than this process asserting it.
 * Nothing here decides whether a detector *would* fire — that is read at
 * verdict time on the deployment, the same as every other observation.
 */

/** One field of an answer that crossed a process, or a stated fallback. */
function pick(record: unknown, name: string, fallback: unknown): unknown {
  const found: unknown = Reflect.get(Object(record), name);
  return found ?? fallback;
}

/** Every operation this courier will forward, and where each goes. */
const OPERATIONS: Readonly<Record<string, { path: string; method: 'POST' }>> = {
  'dry-run': { path: '/dry-run', method: 'POST' },
  enable: { path: '/enable', method: 'POST' },
  disable: { path: '/disable', method: 'POST' },
};

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const detectorId = String(Reflect.get(Object(body), 'detectorId') ?? '');
  const operation = String(Reflect.get(Object(body), 'operation') ?? '');
  const forwarded = OPERATIONS[operation];
  if (detectorId === '' || forwarded === undefined) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/detectors/${encodeURIComponent(detectorId)}${forwarded.path}`;
  try {
    const answer = await fetch(address, {
      method: forwarded.method,
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: '{}',
      cache: 'no-store',
    });
    const answered: unknown = await answer.json().catch(() => ({}));
    // The gateway's own words on a refusal, nested under `error` the way every
    // handler in `gateway/http/errors.py` shapes one — crossed back as they
    // stand rather than replaced with a sentence this process invented.
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
