import type { ReactNode } from 'react';

import { EmptyState } from '@/components/state';
import { CompassIcon } from '@/design/icons';

/**
 * An empty state whose action is a navigation rather than a handler.
 *
 * `EmptyState` accepts a destination as a link, which is right for "go back to
 * the overview": it can be opened in a new tab, copied, and read as an
 * outbound edge without a second control carrying the same label.
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
    <EmptyState
      heading={heading}
      body={body}
      icon={<CompassIcon size="empty" />}
      action={{ label: actionLabel, href }}
    />
  );
}
