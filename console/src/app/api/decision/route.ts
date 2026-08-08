import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * A decision, forwarded to the deployment with the session's own credential.
 *
 * The credential is in an HTTP-only cookie, so a browser cannot present it and a
 * decision made on a screen has to pass through here. That is the whole reason
 * this handler exists — it is a courier, not a decision-maker: it forwards, and
 * it returns the deployment's answer verbatim, status included.
 *
 * **It refuses a rejection with no reason.** The control on the screen refuses
 * one too, and that is not duplication: the control is a courtesy to the person
 * using it and this is the rule. A reason is what the next person reads when the
 * same change is proposed again, and a rejection with no reason is
 * indistinguishable from one nobody got to.
 */

const VERDICTS = new Set(['approve', 'reject']);

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ decided: false }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const interactionId = String(Reflect.get(Object(body), 'interactionId') ?? '');
  const verdict = String(Reflect.get(Object(body), 'verdict') ?? '');
  const reason = String(Reflect.get(Object(body), 'reason') ?? '').trim();

  if (interactionId === '' || !VERDICTS.has(verdict)) {
    return NextResponse.json({ decided: false }, { status: 400 });
  }
  if (verdict === 'reject' && reason === '') {
    return NextResponse.json({ decided: false, reasonRequired: true }, { status: 422 });
  }

  const address = `${apiOrigin()}/v1/interactions/${encodeURIComponent(interactionId)}/${verdict}`;
  try {
    const answer = await fetch(address, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify(verdict === 'reject' ? { reason } : {}),
      cache: 'no-store',
    });
    return NextResponse.json({ decided: answer.ok }, { status: answer.status });
  } catch {
    // A deployment that cannot be reached is not a refused decision, and the
    // difference decides whether somebody retries or goes looking for an outage.
    return NextResponse.json({ decided: false, reachable: false }, { status: 502 });
  }
}
