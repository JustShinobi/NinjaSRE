import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Declaring what this deployment accepts from one integration's certificate.
 *
 * A courier, the same shape as `../credential/`: the session credential is an
 * HTTP-only cookie the browser cannot present itself, so this forwards once,
 * authenticated, and decides nothing. What crosses here is never a secret — a
 * pinned fingerprint and a certificate authority are public by design, which is
 * the whole reason this is a separate route from `../credential/` rather than
 * one more field on it. The one field that *is* sensitive in a different way,
 * `unverifiedReason`, is not a credential either; it is the sentence an audit
 * trail keeps forever, and the permission that gates it (`integration.trust_unverified`)
 * is enforced by the gateway on every request this forwards, never by whether
 * this process chose to send the field.
 *
 * Nothing here decides who may accept an unverified certificate. A caller
 * without the permission gets the gateway's own refusal, naming the permission,
 * forwarded exactly as it arrived — this process invents no wording of its own
 * for a decision it did not make.
 */

/** What the browser sends: which integration, and the declaration's optional parts. */
interface TrustWrite {
  readonly integration: string;
  readonly fingerprints: readonly string[];
  readonly certificatePem: string;
  readonly unverifiedReason: string;
}

/** `value` as a list of non-blank strings, dropping anything that is not one. */
function stringList(value: unknown): readonly string[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (each): each is string => typeof each === 'string' && each.trim() !== '',
  );
}

/** `body` read as a trust declaration, or `null` when it names no integration. */
function asWrite(body: unknown): TrustWrite | null {
  const integration: unknown = Reflect.get(Object(body), 'integration');
  if (typeof integration !== 'string' || integration === '') return null;
  const certificatePem: unknown = Reflect.get(Object(body), 'certificatePem');
  const unverifiedReason: unknown = Reflect.get(Object(body), 'unverifiedReason');
  return {
    integration,
    fingerprints: stringList(Reflect.get(Object(body), 'fingerprints')),
    certificatePem: typeof certificatePem === 'string' ? certificatePem.trim() : '',
    unverifiedReason:
      typeof unverifiedReason === 'string' ? unverifiedReason.trim() : '',
  };
}

/**
 * The gateway's refusal as one readable line.
 *
 * Every error this route can forward — a malformed declaration, a missing
 * `integration.trust_unverified` — crosses as `{"error":{"message": "..."}}`,
 * the envelope every handler in this deployment now writes; `detail` is read
 * too, as a fallback rather than the primary shape, the same defensiveness
 * `../config/route.ts` already applies to a body it did not generate.
 */
function reasonOf(written: unknown): string {
  const error: unknown = Reflect.get(Object(written), 'error');
  const message: unknown = Reflect.get(Object(error), 'message');
  if (typeof message === 'string' && message !== '') return message;
  const detail: unknown = Reflect.get(Object(written), 'detail');
  return typeof detail === 'string' ? detail : '';
}

/** One field of an answer that crossed a process, or a stated fallback. */
function pick(record: unknown, name: string, fallback: unknown): unknown {
  const found: unknown = Reflect.get(Object(record), name);
  return found ?? fallback;
}

/** Declare one integration's certificate trust, and report what the deployment now covers. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const write = asWrite(await request.json().catch(() => null));
  if (write === null) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/integrations/${encodeURIComponent(write.integration)}/trust`;
  try {
    const answer = await fetch(address, {
      method: 'PUT',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({
        fingerprints: write.fingerprints,
        certificate_pem: write.certificatePem === '' ? null : write.certificatePem,
        unverified_reason:
          write.unverifiedReason === '' ? null : write.unverifiedReason,
      }),
      cache: 'no-store',
    });
    const written: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        reason: reasonOf(written),
        anchor: pick(written, 'anchor', ''),
        addresses: pick(written, 'addresses', []),
        describes: pick(written, 'describes', ''),
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
