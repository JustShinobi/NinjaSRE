import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import {
  safeReturnTo,
  SESSION_COOKIE,
  SESSION_EXPIRY_COOKIE,
  SESSION_LIFETIME_SECONDS,
  signInHref,
  type SessionReason,
} from '@/session/cookies';

/**
 * Where a username and a password become a session, and the only place either
 * exists.
 *
 * The pair arrives in a `POST` body and is offered to the **API origin**, which
 * is the one thing that decides whether it is good. What comes back is a token,
 * and that token — never the password — becomes an HTTP-only,
 * `SameSite=Strict` cookie. Nothing is written to a log, put in a URL, returned
 * to the browser, or placed anywhere `document.cookie` or `localStorage` can
 * reach. Nothing in a component can read it, so no bug in a component can leak
 * it.
 *
 * The console does not decide whether a credential is good. It asks the API and
 * believes the answer. A console that checked a password itself would be a
 * second opinion about authentication, and the second opinion is the one that is
 * wrong.
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

/**
 * A 303 to a path on whatever host the browser used.
 *
 * The `Location` is **relative**, which RFC 7231 allows and which is the whole
 * point: an absolute URL here would be built from the address this process was
 * bound to rather than the one in the request, so a console reached by IP, or
 * through a reverse proxy, would send people to `localhost` — or, for a
 * container bound to `0.0.0.0`, to an address that is not reachable at all.
 * Since the session cookie is `SameSite=Strict` and scoped to the host it was
 * set on, that redirect also silently drops the session and loops back to the
 * form.
 */
function seeOther(location: string): NextResponse {
  return new NextResponse(null, { status: 303, headers: { location } });
}

/** Back to the form, saying why, with no session left behind. */
function refused(returnTo: string, reason: SessionReason): NextResponse {
  return withoutSession(seeOther(signInHref(returnTo, reason)));
}

/** What a successful sign-in returns. Read defensively: it crosses a process. */
function tokenOf(payload: unknown): string | null {
  if (typeof payload !== 'object' || payload === null) return null;
  const token: unknown = Reflect.get(payload, 'token');
  return typeof token === 'string' && token !== '' ? token : null;
}

/** Establish a session from a username and a password. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const form = await request.formData();
  const username = form.get('username');
  const password = form.get('password');
  const requested = form.get('returnTo');
  const returnTo = safeReturnTo(typeof requested === 'string' ? requested : null);

  if (
    typeof username !== 'string' ||
    typeof password !== 'string' ||
    username.trim() === '' ||
    password === ''
  ) {
    return refused(returnTo, 'rejected');
  }

  let answer: Response;
  try {
    answer = await fetch(`${apiOrigin()}/auth/sign-in`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify({ username, password }),
      cache: 'no-store',
    });
  } catch {
    // A deployment that cannot be reached is not a rejected credential, and
    // saying so is what stops somebody retyping a password that was always
    // right.
    return refused(returnTo, 'unreachable');
  }

  if (!answer.ok) {
    return refused(returnTo, 'rejected');
  }

  const token = tokenOf(await answer.json().catch(() => null));
  if (token === null) {
    return refused(returnTo, 'unreachable');
  }

  const expiresAt = new Date(Date.now() + MAX_AGE * 1000).toISOString();
  const response = seeOther(returnTo);
  response.cookies.set(SESSION_COOKIE, token, {
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
