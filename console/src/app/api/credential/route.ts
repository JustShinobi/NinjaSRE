import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * A credential on its way to the vault, and the four things this handler does
 * not do with it.
 *
 * It does not **store** it. The value is read out of the request body, put
 * straight into the body of one outbound request, and never assigned anywhere
 * that outlives the call. There is no cache, no cookie and no file.
 *
 * It does not **log** it. Nothing here writes a line at all — not the values,
 * not the field names, not the integration. The gateway logs the field names
 * and the version, which is the record somebody actually needs, and it does it
 * where the audit trail is.
 *
 * It does not **return** it. What comes back is the gateway's own answer, which
 * by construction has no field a value could sit in: an integration, a state, a
 * version, and the field *names*. A refusal is forwarded as the gateway worded
 * it, and the gateway's refusals name fields and never quote one.
 *
 * And it does not put it in a **URL**. A `POST` body, once, with the
 * integration in the body rather than in the path — because a path is a thing
 * that reaches an access log, and a name is not a secret but the habit is.
 *
 * **Why the console carries it at all.** The credential that authenticates this
 * request is an HTTP-only, `SameSite=Strict` cookie set on the console's own
 * host: a browser will not send it to the API origin, and cannot be made to
 * when the two are different hosts. So a form posted straight at the gateway is
 * a form that arrives unauthenticated in every deployment that runs the API
 * anywhere but behind the console's own address. This is the same courier
 * `src/app/api/session/` already is for a *password*, which is a secret of
 * exactly this class, and the property both hold is not "the secret never
 * enters this process" but "this process keeps none of it".
 */

/** What the browser sends: a target and a flat map of field name to value. */
interface CredentialWrite {
  readonly integration: string;
  readonly values: Readonly<Record<string, string>>;
}

/** `body` read as a credential write, or `null` when it is not one. */
function asWrite(body: unknown): CredentialWrite | null {
  const integration: unknown = Reflect.get(Object(body), 'integration');
  const values: unknown = Reflect.get(Object(body), 'values');
  if (typeof integration !== 'string' || integration === '') return null;
  if (typeof values !== 'object' || values === null || Array.isArray(values))
    return null;
  const flat: Record<string, string> = {};
  for (const [name, value] of Object.entries(values)) {
    // A field whose value is not a string is a shape somebody is probing with,
    // not a credential. Dropped rather than coerced: `String({})` is a
    // credential of "[object Object]", which the vault would happily store.
    if (typeof value === 'string') flat[name] = value;
  }
  return { integration, values: flat };
}

/** One field of an answer that crossed a process, or a stated fallback. */
function pick(record: unknown, name: string, fallback: unknown): unknown {
  const found: unknown = Reflect.get(Object(record), name);
  return found ?? fallback;
}

/** Store one credential in the deployment's vault, and report what it now is. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const write = asWrite(await request.json().catch(() => null));
  if (write === null) {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/integrations/${encodeURIComponent(write.integration)}/credential`;
  try {
    const answer = await fetch(address, {
      method: 'PUT',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({ values: write.values }),
      cache: 'no-store',
    });
    const stored: unknown = await answer.json().catch(() => ({}));
    const detail: unknown = Reflect.get(Object(stored), 'detail');
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        // The gateway's own words. It names fields and never quotes one, so it
        // crosses back as it stands.
        reason: typeof detail === 'string' ? detail : '',
        state: pick(stored, 'state', ''),
        version: pick(stored, 'version', 0),
        fields: pick(stored, 'fields', []),
      },
      { status: answer.status },
    );
  } catch {
    // The deployment, not this process. Saying "refused" would send somebody to
    // look at the wrong machine, and they would find nothing wrong with it.
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
