import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * A proposal's two operations, forwarded and never decided here.
 *
 * One courier for both rather than two files, and the closed table below is
 * what keeps that from becoming an open proxy: an operation this handler does
 * not name cannot be reached through it, so the console's own process can never
 * be used to address an arbitrary path on the deployment.
 *
 * **The effect is not computed here and could not be.** What a configuration
 * proposal would resolve to is the configuration service's answer and what a
 * detector would have found is the detector's; both are asked through the
 * mechanisms that already exist, because a second renderer in the console would
 * agree with the deployment right up until the day it did not, and the
 * disagreement surfaces as somebody approving one thing having read another.
 *
 * It exists at all because the credential lives in an HTTP-only cookie, so a
 * browser cannot present it. This is a courier.
 */

/** Every operation this courier will forward, and where each goes. */
const OPERATIONS: Readonly<Record<string, (target: string) => string>> = {
  decide: (target) => `/v1/proposals/${encodeURIComponent(target)}/decision`,
  preview: (target) => `/v1/config/${encodeURIComponent(target)}/preview`,
  'context-preview': (target) =>
    `/v1/config/${encodeURIComponent(target)}/operating-context/preview`,
  'dry-run': (target) => `/v1/detectors/${encodeURIComponent(target)}/dry-run`,
};

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const operation = String(Reflect.get(Object(body), 'operation') ?? '');
  const target = String(Reflect.get(Object(body), 'target') ?? '');
  const payload: unknown = Reflect.get(Object(body), 'payload') ?? {};
  const address = OPERATIONS[operation];
  if (target === '' || address === undefined) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  try {
    const answer = await fetch(`${apiOrigin()}${address(target)}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });
    // Verbatim, including a refusal. The gateway's own sentence is what the
    // reviewer needs to read, and rewording it here would put a second opinion
    // about why something was refused in front of them.
    const answered: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(answered, { status: answer.status });
  } catch {
    return NextResponse.json({ reachable: false }, { status: 502 });
  }
}
