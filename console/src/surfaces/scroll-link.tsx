'use client';

import NextLink from 'next/link';
import type { ReactNode } from 'react';

import { captureScrollPosition } from './scroll-memory';

export interface ScrollCapturingLinkProps {
  readonly href: string;
  readonly className?: string;
  readonly 'data-testid'?: string;
  readonly children: ReactNode;
}

/**
 * A link into the credential panel that remembers the catalogue's scroll
 * position before it navigates, so `IntegrationPanel` can put it back when
 * it closes.
 *
 * The event handler has to live behind its own client boundary: the screen
 * that renders the Connected and Suggested rows is a server component, and a
 * server component cannot hand a client component a function to call — only
 * serialisable props. This is the whole of that boundary, reused at each of
 * the three places a card opens the panel.
 */
export function ScrollCapturingLink({
  href,
  className,
  children,
  ...rest
}: ScrollCapturingLinkProps): ReactNode {
  return (
    <NextLink
      href={href}
      scroll={false}
      className={className}
      onClick={captureScrollPosition}
      {...rest}
    >
      {children}
    </NextLink>
  );
}
