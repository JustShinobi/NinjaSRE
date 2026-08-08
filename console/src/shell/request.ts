import { cookies, headers } from 'next/headers';

import { resolveLocale, type Locale } from '@/i18n/messages';
import {
  LOCALE_COOKIE,
  SESSION_COOKIE,
  SESSION_EXPIRY_COOKIE,
} from '@/session/cookies';

/**
 * What the server knows about one request, in the four things the shell asks.
 *
 * Every one of these reads a request-scoped API, so nothing here can be called
 * from a component that renders in a browser — which is the point. The session
 * credential is reachable on the server and nowhere else, and this module is the
 * boundary that makes that a structural fact rather than a convention.
 */

/** The locale to render in: the viewer's stored choice, then what the browser asks for. */
export async function requestLocale(): Promise<Locale> {
  const stored = (await cookies()).get(LOCALE_COOKIE)?.value ?? null;
  if (stored !== null) {
    return resolveLocale(stored);
  }
  return resolveLocale((await headers()).get('accept-language'));
}

/**
 * The credential this request carries, or `null`.
 *
 * Server-only by construction: the cookie is HTTP-only, so there is no browser
 * code path that could reach it even if one were written.
 */
export async function requestCredential(): Promise<string | null> {
  const value = (await cookies()).get(SESSION_COOKIE)?.value;
  return value === undefined || value === '' ? null : value;
}

/** When this session ends, as the companion cookie records it. */
export async function requestExpiry(): Promise<string | null> {
  return (await cookies()).get(SESSION_EXPIRY_COOKIE)?.value ?? null;
}
