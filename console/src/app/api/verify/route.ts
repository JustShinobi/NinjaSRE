import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Checking one configured thing, for real, because somebody asked.
 *
 * A `POST` rather than something a listing does: verifying a provider makes a
 * live request against the operator's own endpoint and costs them tokens, so it
 * happens when a person presses a control and never while a page renders. The
 * gateway records the same decision, and this keeps it.
 *
 * A courier, like every other write here: the session credential is an
 * HTTP-only cookie the browser cannot read and will not send to another host.
 * No secret passes through this one — a verification names a thing and returns
 * a verdict.
 */

/** The two kinds of thing this deployment can be asked to check. */
const TARGETS = {
  provider: (name: string) => `/v1/providers/${encodeURIComponent(name)}/verify`,
  integration: (name: string) => `/v1/integrations/${encodeURIComponent(name)}/verify`,
} as const;

/**
 * The vendor's own answer, for an integration whose credential already works.
 *
 * A second call, and only where it can tell somebody something. The route above
 * reads what this deployment stored; this one makes live vendor calls, so it is
 * skipped for a provider (which has no such route) and for a credential that is
 * not usable — there is nothing to learn from asking a store to prove it holds
 * data with a key it will reject.
 */
const REPORT = (name: string) =>
  `/v1/integrations/${encodeURIComponent(name)}/verify/report`;

type Target = keyof typeof TARGETS;

function targetOf(value: unknown): Target | null {
  return value === 'provider' || value === 'integration' ? value : null;
}

/**
 * What the deployment measured that makes this source's answers unsafe.
 *
 * A 404 is not a failure here: the route answers it for a deployment that
 * composed no way to reach a vendor and for a vendor with nothing further to be
 * asked, and both of those are working deployments. Empty is the right answer
 * for them, and it renders as no findings rather than as a clean bill.
 */
async function findingsFor(
  name: string,
  credential: string,
): Promise<readonly string[]> {
  try {
    const answer = await fetch(`${apiOrigin()}${REPORT(name)}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: '{}',
      cache: 'no-store',
    });
    if (!answer.ok) return [];
    const body: unknown = await answer.json().catch(() => ({}));
    const found: unknown = Reflect.get(
      Object(Reflect.get(Object(body), 'report')),
      'degradations',
    );
    return Array.isArray(found) ? found.filter((each) => typeof each === 'string') : [];
  } catch {
    return [];
  }
}

/** One field of an answer that crossed a process, or a stated fallback. */
function pick(record: unknown, name: string, fallback: unknown): unknown {
  const found: unknown = Reflect.get(Object(record), name);
  return found ?? fallback;
}

/** Verify one provider or one integration and return the deployment's verdict. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const kind = targetOf(Reflect.get(Object(body), 'kind'));
  const name: unknown = Reflect.get(Object(body), 'name');
  if (kind === null || typeof name !== 'string' || name === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  try {
    const answer = await fetch(`${apiOrigin()}${TARGETS[kind](name)}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: '{}',
      cache: 'no-store',
    });
    const verdict: unknown = await answer.json().catch(() => ({}));
    const detail: unknown = Reflect.get(Object(verdict), 'detail');
    const remedy: unknown = Reflect.get(Object(verdict), 'remedy');
    const problem: unknown = Reflect.get(Object(verdict), 'detail');
    // "Configured" and "it answered" are different facts and the two routes
    // report them under different names. Collapsed here into one word for the
    // caller, and never into one *claim*: a credential that is merely present
    // comes back `false`.
    const verified =
      Reflect.get(Object(verdict), 'verified') === true ||
      Reflect.get(Object(verdict), 'usable') === true;
    const findings =
      kind === 'integration' && answer.ok && verified
        ? await findingsFor(name, credential)
        : [];
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        verified: answer.ok && verified,
        reason: typeof (answer.ok ? detail : problem) === 'string' ? detail : '',
        remedy: typeof remedy === 'string' ? remedy : '',
        state: pick(verdict, 'state', ''),
        alternatives: pick(verdict, 'alternatives', []),
        findings,
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
