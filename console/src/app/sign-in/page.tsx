import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { message } from '@/i18n/messages';
import {
  isSessionReason,
  RETURN_TO_PARAM,
  SESSION_REASON_PARAM,
} from '@/session/cookies';
import { safeReturnTo } from '@/session/cookies';
import { requestLocale } from '@/shell/request';
import { NoAdministratorNotice } from '@/surfaces/no-administrator-notice';
import { localAdministratorAvailability } from '@/surfaces/read';

/**
 * The only thing an unauthenticated visitor sees, and it says nothing.
 *
 * No deployment name, no version, no organisation, no count of anything. A
 * sign-in page that names the deployment tells whoever reached it that there is
 * a deployment here and what it is called, and that is one fact more than
 * somebody who has not signed in is owed.
 *
 * The form posts a username and a password in a body to a route handler, which
 * offers them to the API and keeps the token it gets back in an HTTP-only
 * cookie. Neither is ever in the URL — a query parameter is in the browser's
 * history, in the proxy's access log, and in the `Referer` of the next request.
 */
export const dynamic = 'force-dynamic';

/**
 * What each arrival is told, when it is worth saying anything.
 *
 * `signed-out` is absent on purpose: somebody who signed out knows why they are
 * here, and a page that explains it is a page that argues with them.
 */
const REASON_MESSAGE = {
  expired: 'signIn.expired',
  rejected: 'signIn.rejected',
  unreachable: 'signIn.unreachable',
} as const;

export function generateMetadata(): Metadata {
  // Deliberately not the deployment's name. Every other page carries it; this
  // one is shown to people who have not established that they may know it.
  return { title: 'Sign in' };
}

export default async function SignIn({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const locale = await requestLocale();
  const parameters = await searchParams;
  const raw = parameters[RETURN_TO_PARAM];
  const returnTo = safeReturnTo(typeof raw === 'string' ? raw : null);
  const reasonRaw = parameters[SESSION_REASON_PARAM];
  const reason = typeof reasonRaw === 'string' ? reasonRaw : null;
  const availability = await localAdministratorAvailability();

  return (
    <main data-testid="sign-in" className="mx-auto flex max-w-prose flex-col gap-4 p-7">
      <h1 className="text-title">{message(locale, 'signIn.title')}</h1>
      <p className="text-small text-muted">{message(locale, 'signIn.context')}</p>
      {isSessionReason(reason) && reason !== 'none' && reason !== 'signed-out' ? (
        <p
          data-testid="sign-in-reason"
          role="status"
          className={
            reason === 'expired' ? 'text-small text-warning' : 'text-small text-danger'
          }
        >
          {message(locale, REASON_MESSAGE[reason])}
        </p>
      ) : null}
      <NoAdministratorNotice
        command={availability.command}
        labels={{
          title: message(locale, 'noAdministrator.title'),
          body: message(locale, 'noAdministrator.body'),
        }}
      />
      <form
        method="post"
        action="/api/session"
        data-testid="sign-in-form"
        className="flex flex-col gap-3"
      >
        <label htmlFor="username" className="text-small">
          {message(locale, 'signIn.username')}
        </label>
        <input
          id="username"
          name="username"
          type="text"
          required
          autoComplete="username"
          autoFocus
          spellCheck={false}
          className="rounded-2 edge border-border bg-surface px-3 py-2 text-small"
        />
        <label htmlFor="password" className="text-small">
          {message(locale, 'signIn.password')}
        </label>
        <input
          id="password"
          name="password"
          type="password"
          required
          autoComplete="current-password"
          spellCheck={false}
          className="rounded-2 edge border-border bg-surface px-3 py-2 text-small"
        />
        <input type="hidden" name="returnTo" value={returnTo} />
        <button
          type="submit"
          className="rounded-2 bg-accent px-4 py-2 text-body font-semibold text-on-accent"
        >
          {message(locale, 'signIn.submit')}
        </button>
      </form>
    </main>
  );
}
