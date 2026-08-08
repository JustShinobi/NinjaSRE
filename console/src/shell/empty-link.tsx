'use client';

import type { ReactNode } from 'react';

import { EmptyState } from '@/components/state';
import { CompassIcon } from '@/design/icons';

/**
 * An empty state whose action is a navigation rather than a handler.
 *
 * `EmptyState` takes a callback, which is right for the screens that do
 * something — but "go back to the overview" is a link, and a link that is
 * actually a button cannot be opened in a new tab, cannot be copied, and is
 * invisible to anything that reads a page for its outbound edges.
 *
 * So this is a thin client wrapper: the same primitive, with the callback wired
 * to a real navigation, in the one place the console needs one.
 */
export interface EmptyStateLinkProps {
  readonly heading: string;
  readonly body: string;
  readonly actionLabel: string;
  readonly href: string;
}

export function EmptyStateLink({
  heading,
  body,
  actionLabel,
  href,
}: EmptyStateLinkProps): ReactNode {
  return (
    <>
      <EmptyState
        heading={heading}
        body={body}
        icon={<CompassIcon size="empty" />}
        action={{
          label: actionLabel,
          onSelect: () => {
            window.location.assign(href);
          },
        }}
      />
      {/* The same destination as a real link, for anything that reads edges
          rather than presses buttons — a crawler, a reader mode, a keyboard
          user who tabs past the illustration. */}
      <a href={href} className="sr-only" data-testid="way-back">
        {actionLabel}
      </a>
    </>
  );
}
