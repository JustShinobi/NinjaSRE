'use client';

import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { message, type Locale } from '@/i18n/messages';
import { readFailure } from '@/surfaces/failures';
import { oldest, type AttentionItem } from './attention';

/**
 * What is waiting on a person, in one place, with a count.
 *
 * The count is the whole reason it exists: an operator wants to know whether
 * anything needs them without opening four screens. What makes it worth
 * trusting is the other half — an item resolved anywhere else is gone from here
 * without a refresh, because the list is state the shell holds and every
 * surface that resolves something tells the shell so.
 *
 * A notification centre still showing an approval somebody granted five minutes
 * ago is one people stop reading, and a list nobody reads is worse than no list
 * at all: it makes "nothing is waiting" indistinguishable from "I did not look".
 *
 * A failed run's summary is whatever the deployment put there, and for the
 * failure that matters most that is a raised exception naming an environment
 * variable. It is translated here, at the point of rendering, rather than by
 * the loader: what to *say* about a failure is a presentation decision, and a
 * loader that made it would have to be handed a locale to read a list.
 */

export interface NotificationCentreProps {
  readonly open: boolean;
  readonly locale: Locale;
  readonly items: readonly AttentionItem[];
  readonly onClose: () => void;
}

/**
 * What one row says, once a raised exception has been turned into a sentence.
 *
 * Only failures are translated, and only where the console recognises what went
 * wrong or can tell that the text is an exception at all. Everything else — an
 * approval's summary, an incident's title, a run summary somebody wrote — is a
 * sentence already, and is left exactly as the deployment worded it.
 *
 * The link moves too, where the translation knows a better destination: the
 * run that failed because nothing is configured is not the screen that fixes
 * it, and sending somebody to the transcript of a run that never started is the
 * same dead end in a different colour.
 */
function spoken(
  item: AttentionItem,
  locale: Locale,
): { title: string; detail: string; href: string } {
  if (item.kind !== 'failure') {
    return { title: item.title, detail: item.detail, href: item.href };
  }
  const read = readFailure(item.title, locale);
  if (read.technical === '') {
    return { title: item.title, detail: item.detail, href: item.href };
  }
  return {
    title: read.title,
    detail: read.action,
    href: read.href === '' ? item.href : read.href,
  };
}

export function NotificationCentre({
  open,
  locale,
  items,
  onClose,
}: NotificationCentreProps): ReactNode {
  if (!open) {
    return null;
  }
  const first = oldest(items);
  return (
    <aside
      data-testid="notifications"
      aria-label={message(locale, 'notifications.title')}
      className="absolute right-0 z-10 flex w-max max-w-prose flex-col rounded-3 edge border-border bg-raised shadow-2"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <p className="flex items-center gap-3 p-3 edge border-x-0 border-t-0 border-border">
        <span className="text-strong">{message(locale, 'notifications.title')}</span>
        <span data-testid="notification-count" className="ml-auto text-meta text-muted">
          {message(locale, 'notifications.unread', { count: items.length })}
        </span>
      </p>
      {items.length === 0 ? (
        <p data-testid="notifications-empty" className="p-4 text-small text-muted">
          {message(locale, 'notifications.empty')}
        </p>
      ) : (
        <ul className="flex flex-col">
          {items.map((item) => {
            const said = spoken(item, locale);
            return (
              <li key={item.id}>
                <a
                  href={said.href}
                  data-testid="notification"
                  data-item={item.id}
                  data-oldest={item.id === first?.id ? 'true' : undefined}
                  className="flex items-start gap-3 p-3 edge border-x-0 border-t-0 border-border motion-hover hover:bg-hover"
                >
                  <Badge status={item.kind} />
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-small">{said.title}</span>
                    <span className="truncate text-meta text-muted">{said.detail}</span>
                  </span>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
