import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Saving a configuration patch, forwarded and never computed.
 *
 * The sibling of `../preview/`, and deliberately the same shape: the browser
 * asks what saving would resolve to, a person reads the deployment's answer,
 * and then the identical patch is sent here. A handler that merged, defaulted
 * or reordered anything would break that pairing — the preview would be of one
 * document and the write of another, which is the failure the preview exists to
 * prevent.
 *
 * It exists because the credential is in an HTTP-only cookie and a browser
 * cannot present it. This is a courier, and no credential ever travels through
 * this one: a configuration patch that carried a secret would be refused by the
 * gateway, which is the boundary that decides it rather than this.
 */

/** One field of an answer that crossed a process, or a stated fallback. */
function pick(record: unknown, name: string, fallback: unknown): unknown {
  const found: unknown = Reflect.get(Object(record), name);
  return found ?? fallback;
}

/**
 * The gateway's refusal as one readable line.
 *
 * A `detail` is a string when the gateway wrote a sentence, and a structure
 * when its validation layer spoke — a list of paths and messages. Both are
 * words somebody typed for a person to read, so both come through; a courier
 * that forwarded only the string turned every structured refusal into
 * "refused:" with nothing after the colon.
 */
function reasonOf(written: unknown): string {
  const detail: unknown = Reflect.get(Object(written), 'detail');
  if (typeof detail === 'string') return detail;
  if (detail === undefined || detail === null) return '';
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => {
        const path: unknown = Reflect.get(Object(entry), 'path');
        const message: unknown =
          Reflect.get(Object(entry), 'message') ?? Reflect.get(Object(entry), 'msg');
        return [path, message].filter((part) => typeof part === 'string').join(' ');
      })
      .filter((line) => line !== '')
      .join('; ');
  }
  return JSON.stringify(detail);
}

/** Write a configuration patch at one node and return what now applies there. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const nodeId = String(Reflect.get(Object(body), 'nodeId') ?? '');
  const patch: unknown = Reflect.get(Object(body), 'patch');
  if (nodeId === '' || typeof patch !== 'object' || patch === null) {
    // Named, not just numbered: the screen prints this after "refused:", and
    // a 400 whose body carried no words rendered as a colon and nothing.
    return NextResponse.json(
      {
        ok: false,
        reachable: true,
        reason:
          nodeId === '' ? 'the request named no node' : 'the request carried no patch',
      },
      { status: 400 },
    );
  }

  try {
    const answer = await fetch(
      `${apiOrigin()}/v1/config/${encodeURIComponent(nodeId)}`,
      {
        method: 'PUT',
        headers: {
          authorization: `Bearer ${credential}`,
          'content-type': 'application/json',
          accept: 'application/json',
        },
        body: JSON.stringify({ patch }),
        cache: 'no-store',
      },
    );
    const written: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        reason: reasonOf(written),
        values: pick(written, 'values', {}),
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
