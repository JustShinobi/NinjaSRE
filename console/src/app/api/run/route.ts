import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Steering a run: starting one, adding to one, taking one over, handing it back,
 * ending it.
 *
 * A courier, like every other handler under `src/app/api/`. It exists because
 * the credential is in an HTTP-only cookie and a browser cannot present it; it
 * decides nothing about the run.
 *
 * What it *does* decide is the shape of the answer, and that is load-bearing for
 * the optimism this feature is built on. A refused write comes back with the
 * deployment's own status and the deployment's own reason, so the control that
 * applied the change immediately can put the old value back and say why. A
 * handler that flattened every refusal into "that did not work" would leave the
 * operator with a screen that reverted for no stated cause, which is worse than
 * not being optimistic at all.
 */

/** What may be asked of a run, and the path each one is. */
const RUN_ACTIONS: Readonly<Record<string, string>> = {
  cancel: 'cancel',
  'take-over': 'take-over',
  resume: 'resume',
  message: 'messages',
};

/** What comes back from a refusal, in the deployment's own words. */
function reasonIn(body: unknown): string {
  for (const key of ['detail', 'message', 'reason']) {
    const found: unknown = Reflect.get(Object(body), key);
    if (typeof found === 'string' && found !== '') return found;
  }
  return '';
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ applied: false }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const runId = String(Reflect.get(Object(body), 'runId') ?? '');
  const action = String(Reflect.get(Object(body), 'action') ?? '');
  const text = String(Reflect.get(Object(body), 'text') ?? '').trim();

  const headers = {
    authorization: `Bearer ${credential}`,
    'content-type': 'application/json',
    accept: 'application/json',
  };

  if (action === 'start') {
    // The one action with no run to act on, because it is what produces one.
    if (text === '') return NextResponse.json({ applied: false }, { status: 400 });
    return forward(`${apiOrigin()}/v1/investigations`, headers, { objective: text });
  }

  const path = RUN_ACTIONS[action];
  if (runId === '' || path === undefined) {
    return NextResponse.json({ applied: false }, { status: 400 });
  }
  // An empty note is not context. Queuing one would spend a turn of the run
  // delivering nothing, which is a cost with no reader.
  if (action === 'message' && text === '') {
    return NextResponse.json({ applied: false }, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/investigations/${encodeURIComponent(runId)}/${path}`;
  return forward(address, headers, action === 'message' ? { text } : {});
}

async function forward(
  address: string,
  headers: Readonly<Record<string, string>>,
  payload: unknown,
): Promise<NextResponse> {
  try {
    const answer = await fetch(address, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      cache: 'no-store',
    });
    const returned: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(
      {
        applied: answer.ok,
        runId: String(Reflect.get(Object(returned), 'run_id') ?? ''),
        status: String(Reflect.get(Object(returned), 'status') ?? ''),
        reason: answer.ok ? '' : reasonIn(returned),
      },
      { status: answer.status },
    );
  } catch {
    // A deployment that cannot be reached is not a refused write, and the
    // difference decides whether somebody retries or goes looking for an outage.
    return NextResponse.json({ applied: false, reachable: false }, { status: 502 });
  }
}
