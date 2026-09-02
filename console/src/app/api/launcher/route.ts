import { NextResponse, type NextRequest } from 'next/server';

import { SESSION_COOKIE } from '@/session/cookies';
import { EMPTY_BRIEFING } from '@/shell/launcher';
import { loadLauncher, loadViewer } from '@/shell/load';

/**
 * What the investigate drawer opens with: where the environment already is.
 *
 * A courier like every other route under `src/app/api/`, and here for the same
 * reason: the session credential is an HTTP-only cookie the browser cannot
 * read, so a request the browser makes straight at the gateway arrives
 * unauthenticated wherever the two are different hosts.
 *
 * It exists because the briefing costs three gateway reads — the incident
 * listing, the estate summary and the organisation tree — and the frame used
 * to pay for them on every render of every screen, to fill a drawer most page
 * views never open. The drawer asks here when it opens instead, and this does
 * exactly what the frame used to, for that one viewer.
 *
 * The team is the viewer's own, resolved from the session, never read from the
 * request. A courier that let the browser name a team would answer with
 * somebody else's briefing. `/auth/me` is cached by the token service, so
 * resolving the viewer again here is cheap.
 */

export const dynamic = 'force-dynamic';

/** The briefing for the viewer this session belongs to. */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json(EMPTY_BRIEFING, { status: 401 });
  }

  const viewer = await loadViewer(credential).catch(() => null);
  if (viewer === null) {
    // A cookie the deployment no longer accepts is a session event, and the
    // session controller is what handles one. Answering 401 lets it.
    return NextResponse.json(EMPTY_BRIEFING, { status: 401 });
  }

  return NextResponse.json(await loadLauncher(credential, viewer.teamNodeId));
}
