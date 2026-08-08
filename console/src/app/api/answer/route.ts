import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * An agent's question, answered where it was asked.
 *
 * Answering is what resumes the run: the interaction is what the agent is
 * blocked on, and closing it is the only thing that unblocks it. So this is not
 * "record a reply" — it is the resumption, and treating it as a note somebody
 * files would leave a run waiting on a question that had been answered.
 *
 * **It refuses an empty answer.** The control on the screen refuses one too,
 * and that is not duplication: the control is a courtesy to the person using it
 * and this is the rule. A run resumed with nothing has been told that its
 * question was answered and has no answer to act on.
 */

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ answered: false }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const interactionId = String(Reflect.get(Object(body), 'interactionId') ?? '');
  const text = String(Reflect.get(Object(body), 'text') ?? '').trim();
  const option = String(Reflect.get(Object(body), 'option') ?? '');

  if (interactionId === '' || text === '') {
    return NextResponse.json({ answered: false }, { status: 400 });
  }

  const address = `${apiOrigin()}/v1/interactions/${encodeURIComponent(interactionId)}/answer`;
  try {
    const answer = await fetch(address, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${credential}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify(
        option === '' ? { text } : { text, selected_option: option },
      ),
      cache: 'no-store',
    });
    const returned: unknown = await answer.json().catch(() => ({}));
    return NextResponse.json(
      {
        answered: answer.ok,
        reason: answer.ok ? '' : String(Reflect.get(Object(returned), 'detail') ?? ''),
      },
      { status: answer.status },
    );
  } catch {
    return NextResponse.json({ answered: false, reachable: false }, { status: 502 });
  }
}
