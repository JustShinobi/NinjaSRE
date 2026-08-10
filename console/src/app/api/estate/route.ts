import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Onboarding an estate, in the three steps somebody actually takes.
 *
 * A courier, for the reason every other write here is one: the session
 * credential is an HTTP-only, `SameSite=Strict` cookie set on the console's own
 * host, so a browser will not send it to the API origin and cannot be made to
 * when the two are different hosts. Nothing secret passes through this handler
 * — the credential itself goes through `../credential`, and what these three
 * carry is a vendor name, a report, and some counts.
 *
 * **`report`** runs the integration's own verifier against the cluster. It is a
 * `POST` and it happens when somebody presses a control, never on render: it
 * makes several live calls against somebody's hypervisor.
 *
 * **`preview`** runs discovery and stores nothing. This is the step that turns
 * a form into a confirmation — the operator reads "2 nodes, 57 containers, 49
 * running, 7 zones" and recognises their own cluster. If they do not, there is
 * nothing to undo.
 *
 * **`confirm`** registers the recurring sweep. Only after the preview, because
 * the whole point of the preview is that it comes first.
 */

/** What the browser may ask for, and where each one goes. */
const ACTIONS = {
  report: (name: string) =>
    `/v1/integrations/${encodeURIComponent(name)}/verify/report`,
  preview: () => `/v1/estate/discovery/preview`,
  confirm: () => `/v1/estate/discovery/sources`,
} as const;

type Action = keyof typeof ACTIONS;

function actionOf(value: unknown): Action | null {
  return value === 'report' || value === 'preview' || value === 'confirm'
    ? value
    : null;
}

/** A flat CIDR-to-zone-name map read out of a request body, or an empty one. */
function zonesOf(value: unknown): Readonly<Record<string, string>> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return {};
  const flat: Record<string, string> = {};
  for (const [cidr, name] of Object.entries(value)) {
    if (typeof name === 'string' && name !== '') flat[cidr] = name;
  }
  return flat;
}

/** One field of an answer that crossed a process, or a stated fallback. */
function pick(record: unknown, name: string, fallback: unknown): unknown {
  const found: unknown = Reflect.get(Object(record), name);
  return found ?? fallback;
}

/** Ask the deployment one of the three onboarding questions and forward the answer. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const action = actionOf(Reflect.get(Object(body), 'action'));
  const integration: unknown = Reflect.get(Object(body), 'integration');
  if (action === null || typeof integration !== 'string' || integration === '') {
    return NextResponse.json({ ok: false, reachable: true }, { status: 400 });
  }

  const payload =
    action === 'report'
      ? '{}'
      : JSON.stringify({
          integration,
          ...(action === 'preview'
            ? { zones: zonesOf(Reflect.get(Object(body), 'zones')) }
            : {}),
        });

  try {
    const answer = await fetch(`${apiOrigin()}${ACTIONS[action](integration)}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: payload,
      cache: 'no-store',
    });
    const result: unknown = await answer.json().catch(() => ({}));
    // The gateway's own words on a refusal. They name what is missing and the
    // next step, so they cross back as they stand rather than being replaced
    // with a sentence this process invented.
    const problem: unknown = pick(Object(pick(result, 'error', {})), 'message', '');
    return NextResponse.json(
      {
        ok: answer.ok,
        reachable: true,
        reason: typeof problem === 'string' ? problem : '',
        result: answer.ok ? result : {},
      },
      { status: answer.status },
    );
  } catch {
    // The deployment, not this process. Saying "refused" would send somebody to
    // look at the wrong machine, and they would find nothing wrong with it.
    return NextResponse.json({ ok: false, reachable: false }, { status: 502 });
  }
}
