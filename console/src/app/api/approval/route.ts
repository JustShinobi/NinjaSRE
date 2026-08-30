import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * An approval's decision, forwarded to the deployment with the session's own
 * credential.
 *
 * A separate courier from `api/proposal`, deliberately. That one addresses
 * `AgentProposal` — a configuration edit, a detector, a knowledge write, a
 * prompt change — through `/v1/proposals/{id}/decision`. An incident's
 * proposed remediation is a plain `ApprovalRequest` decided directly at the
 * approval store through `/v1/approvals/{id}/decision`, and it is not one of
 * the agent's proposal types; folding it into the other courier's closed
 * operation table would make one file answer for two backend concepts that
 * happen to share a verb.
 *
 * The credential is in an HTTP-only cookie, so a browser cannot present it —
 * this is a courier, not a decision-maker: it forwards, and it returns the
 * deployment's answer verbatim, status included.
 */

/** Every operation this courier will forward, and where each goes. */
const OPERATIONS: Readonly<Record<string, (target: string) => string>> = {
  decide: (target) => `/v1/approvals/${encodeURIComponent(target)}/decision`,
  // Reproposing and discarding both manage an expired approval rather than
  // deciding one — the same store, the same courier, a different verb.
  repropose: (target) => `/v1/approvals/${encodeURIComponent(target)}/repropose`,
  discard: (target) => `/v1/approvals/${encodeURIComponent(target)}/discard`,
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
    // reviewer needs to read, and rewording it here would put a second
    // opinion about why something was refused in front of them.
    const answered: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(answered, { status: answer.status });
  } catch {
    return NextResponse.json({ reachable: false }, { status: 502 });
  }
}
