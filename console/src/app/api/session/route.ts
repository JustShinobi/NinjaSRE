import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import {
  safeReturnTo,
  SESSION_COOKIE,
  SESSION_EXPIRY_COOKIE,
  SESSION_LIFETIME_SECONDS,
} from '@/session/cookies';

/**
 * Where a credential is exchanged for a session, and the only place it exists.
 *
 * The credential arrives in a `POST` body, is offered to the **API origin** to
 * see whether it is accepted, and — if it is — becomes an HTTP-only,
 * `SameSite=Strict` cookie. It is never written to a log, never put in a URL,
 * never returned to the browser, and never placed anywhere `document.cookie` or
 * `localStorage` can reach. Nothing in a component can read it, so no bug in a
 * component can leak it.
 *
 * The console does not decide whether a credential is good. It asks the API,
 * with the credential, and believes the answer. A console that validated a token
 * itself would be a second opinion about authentication, and the second opinion
 * is the one that is wrong.
 *
 * A second cookie carries the expiry, and only the expiry. It is readable on
 * purpose: the warning has to be rendered *before* the session ends, so the
 * browser has to know when that is, and an instant is not a secret.
 */

/** How long the cookie lives, in seconds. */
const MAX_AGE = SESSION_LIFETIME_SECONDS;

function withoutSession(response: NextResponse): NextResponse {
  response.cookies.set(SESSION_COOKIE, '', { path: '/', maxAge: 0 });
  response.cookies.set(SESSION_EXPIRY_COOKIE, '', { path: '/', maxAge: 0 });
  return response;
}

/** Establish a session from a credential the viewer supplied. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const form = await request.formData();
  const credential = form.get('credential');
  const requested = form.get('returnTo');
  const returnTo = safeReturnTo(typeof requested === 'string' ? requested : null);
  if (typeof credential !== 'string' || credential.trim() === '') {
    return NextResponse.json({ accepted: false }, { status: 400 });
  }

  let accepted = false;
  try {
    const answer = await fetch(`${apiOrigin()}/auth/me`, {
      headers: { authorization: `Bearer ${credential}`, accept: 'application/json' },
      cache: 'no-store',
    });
    accepted = answer.ok;
  } catch {
    // A deployment that cannot be reached is not a rejected credential, and
    // saying so is what stops somebody retyping a token that was always right.
    return NextResponse.json({ accepted: false, reachable: false }, { status: 502 });
  }

  if (!accepted) {
    return withoutSession(NextResponse.json({ accepted: false }, { status: 401 }));
  }

  const expiresAt = new Date(Date.now() + MAX_AGE * 1000).toISOString();
  const response = NextResponse.redirect(new URL(returnTo, request.nextUrl), {
    // 303, so the browser follows with a GET. A 307 would replay the POST — and
    // the body of that POST is the credential.
    status: 303,
  });
  response.cookies.set(SESSION_COOKIE, credential, {
    httpOnly: true,
    sameSite: 'strict',
    // Set whenever the console is served over TLS. Left off for a plain-HTTP
    // deployment because a `Secure` cookie is simply never sent there, which
    // would be a console nobody can sign in to rather than a safer one.
    secure: request.nextUrl.protocol === 'https:',
    path: '/',
    maxAge: MAX_AGE,
  });
  response.cookies.set(SESSION_EXPIRY_COOKIE, expiresAt, {
    httpOnly: false,
    sameSite: 'strict',
    secure: request.nextUrl.protocol === 'https:',
    path: '/',
    maxAge: MAX_AGE,
  });
  return response;
}

/** End the session, here and now. */
export function DELETE(): NextResponse {
  return withoutSession(NextResponse.json({ accepted: false }));
}
