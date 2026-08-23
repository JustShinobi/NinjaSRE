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
 * The vendor's own answer, which for an integration is the answer that counts.
 *
 * A second call, made for every integration this deployment could answer for.
 * It used to be made only where the first call had already reported a usable
 * credential, and that gate was the defect: a self-hosted vendor that ships no
 * authentication stores no credential, so the first answer carries no
 * information about it at all — and the one call that could have said whether
 * the thing works was the one being skipped.
 *
 * Still never made for a provider, which has no such route.
 */
const REPORT = (name: string) =>
  `/v1/integrations/${encodeURIComponent(name)}/verify/report`;

type Target = keyof typeof TARGETS;

function targetOf(value: unknown): Target | null {
  return value === 'provider' || value === 'integration' ? value : null;
}

/** What the vendor itself said, as much of it as a chip and a line can carry. */
interface VendorAnswer {
  /** Whether the vendor answered and granted every permission that was probed. */
  readonly ok: boolean;
  /** The vendor's own sentence: "401 Unauthorized", "Alertmanager answered." */
  readonly detail: string;
  /** Measured facts that make the vendor's answers unsafe to trust whole. */
  readonly degradations: readonly string[];
}

async function reportFor(
  name: string,
  credential: string,
): Promise<VendorAnswer | null> {
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
    // A 404 is a working deployment. The route answers it for one that composed
    // no way to reach a vendor and for a vendor with nothing further to be
    // asked, and in both cases the credential state already fetched is the best
    // answer there is — `null`, so the caller falls back to it rather than
    // reading "the vendor said nothing" as "the vendor said no".
    if (!answer.ok) return null;
    const body: unknown = await answer.json().catch(() => ({}));
    const report: unknown = Reflect.get(Object(body), 'report');
    const connectivity: unknown = Reflect.get(Object(report), 'connectivity');
    const said: unknown = Reflect.get(Object(connectivity), 'detail');
    const found: unknown = Reflect.get(Object(report), 'degradations');
    return {
      ok: Reflect.get(Object(report), 'ok') === true,
      detail: typeof said === 'string' ? said : '',
      degradations: Array.isArray(found)
        ? found.filter((each): each is string => typeof each === 'string')
        : [],
    };
  } catch {
    return null;
  }
}

/** One field of an answer that crossed a process, or a stated fallback. */
function pick(record: unknown, name: string, fallback: unknown): unknown {
  const found: unknown = Reflect.get(Object(record), name);
  return found ?? fallback;
}

/**
 * The preflight's own checks, mirrored rather than translated.
 *
 * `[]` for an integration's verdict, which carries no such breakdown — the
 * per-check hierarchy is a provider-verification fact.
 */
function checksOf(verdict: unknown): readonly Record<string, unknown>[] {
  const found: unknown = Reflect.get(Object(verdict), 'checks');
  return Array.isArray(found)
    ? found.filter(
        (each): each is Record<string, unknown> =>
          typeof each === 'object' && each !== null,
      )
    : [];
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
    const vendor =
      kind === 'integration' && answer.ok ? await reportFor(name, credential) : null;
    // The vendor's answer wins where there is one. "A credential is stored" and
    // "the thing works" are different claims, and this is the only place the
    // second one can be made — so a vault that is happy with a key the vendor
    // rejects reports failing, and a vendor that answers with no credential at
    // all reports verified.
    const said = vendor === null ? '' : vendor.detail;
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        verified: answer.ok && (vendor === null ? verified : vendor.ok),
        degraded: vendor !== null && vendor.ok && vendor.degradations.length > 0,
        reason:
          said !== ''
            ? said
            : typeof (answer.ok ? detail : problem) === 'string'
              ? detail
              : '',
        remedy: typeof remedy === 'string' ? remedy : '',
        state: pick(verdict, 'state', ''),
        alternatives: pick(verdict, 'alternatives', []),
        findings: vendor === null ? [] : vendor.degradations,
        checks: checksOf(verdict),
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
