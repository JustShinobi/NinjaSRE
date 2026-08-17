import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Which models a provider's own endpoint currently serves.
 *
 * A courier, like `/api/verify` beside it — the session credential is an
 * HTTP-only cookie the browser cannot read, and no vendor credential ever
 * passes through here: the gateway resolves that itself, from the vault.
 *
 * `GET`, unlike verification: listing spends no tokens, so a page may ask on
 * every render. `refresh=true` is the one case that still means something —
 * an operator's own "Reload models" ignoring the deployment's cache.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json(
      { models: [], source: 'static', reason: 'not signed in' },
      { status: 401 },
    );
  }

  const provider = request.nextUrl.searchParams.get('provider');
  if (provider === null || provider === '') {
    return NextResponse.json(
      { models: [], source: 'static', reason: 'no provider named' },
      { status: 400 },
    );
  }
  const refresh = request.nextUrl.searchParams.get('refresh') === 'true';

  try {
    const path = `/v1/providers/${encodeURIComponent(provider)}/models${refresh ? '?refresh=true' : ''}`;
    const answer = await fetch(`${apiOrigin()}${path}`, {
      method: 'GET',
      headers: {
        authorization: `Bearer ${credential}`,
        accept: 'application/json',
      },
      cache: 'no-store',
    });
    const body: unknown = await answer.json().catch(() => ({}));
    if (!answer.ok) {
      return NextResponse.json(
        { models: [], source: 'static', reason: 'the deployment could not be reached' },
        { status: answer.status },
      );
    }
    return NextResponse.json(body, { status: 200 });
  } catch {
    return NextResponse.json(
      { models: [], source: 'static', reason: 'the deployment could not be reached' },
      { status: 502 },
    );
  }
}
