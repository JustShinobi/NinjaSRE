'use client';

import type { ReactNode } from 'react';

import { ErrorState } from '@/components/state';
import { message } from '@/i18n/messages';
import { useBrowserLocale } from '@/shell/browser';

/**
 * A page that failed, contained to the page.
 *
 * Next mounts this in place of the route's own body and leaves the layout
 * standing, which is exactly the property FR-004 asks for: the sidebar, the
 * utility bar and the palette keep working while one screen is broken. What has
 * to be added is the way back — `reset()` re-renders the segment without
 * reloading the document, so retrying costs a fetch rather than a cold start.
 *
 * The error itself is not rendered. A stack trace on an operations console is a
 * paste into a chat channel, and what it pastes is whatever the exception
 * happened to carry — a URL with a query string in it, more often than not.
 */
export default function RouteError({
  error,
  reset,
}: {
  readonly error: Error & { readonly digest?: string };
  readonly reset: () => void;
}): ReactNode {
  // Next mounts this outside the layout that resolves the locale on the server,
  // so this is the one place the console reads it in a browser.
  const locale = useBrowserLocale();

  return (
    <div data-testid="route-error">
      <ErrorState
        heading={message(locale, 'error.title')}
        detail={message(locale, 'error.context')}
        // The digest is the one thing worth showing: it is what correlates this
        // page with a line in the deployment's own log, and it carries nothing
        // of what the exception happened to be holding.
        dependency={error.digest ?? ''}
        retryLabel={message(locale, 'error.retry')}
        onRetry={reset}
      />
    </div>
  );
}
