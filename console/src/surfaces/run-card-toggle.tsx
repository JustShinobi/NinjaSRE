'use client';

import NextLink, { useLinkStatus } from 'next/link';
import { useCallback, useEffect, useState, type ReactNode } from 'react';

import { ChevronDownIcon, ChevronRightIcon } from '@/design/icons';

/**
 * The row somebody presses to open an investigation, and the two things it
 * owes them while the deployment answers.
 *
 * Opening a card is a router transition, not a document load, and that swapped
 * one problem for another. A reload had the browser's own progress bar and
 * swallowed a second press while it ran; a transition has neither. So a press
 * whose answer took a few hundred milliseconds looked like a press that had
 * not registered, the reader pressed again, and the second press was the
 * toggle's other half — the card they had just opened closed under them. From
 * the outside that is "I click and nothing expands", and the way out people
 * find is reloading the page.
 *
 * Both halves are needed and neither is enough alone. **Saying so**: the
 * chevron becomes a pending mark, and `aria-busy` says the same thing to a
 * reader who is not looking at it. **Meaning it**: while this link is the one
 * being navigated, activating it again does nothing, because the only thing a
 * second press on *this* toggle can do is undo the first. Another card's
 * toggle is a different link with its own pending state, so the list stays
 * responsive — a reader who changes their mind mid-transition still gets the
 * card they asked for second.
 */

/**
 * Publishes the enclosing link's pending state outward.
 *
 * `useLinkStatus` reports on the nearest enclosing link, so it can only be
 * asked from inside one — the same reason the sidebar's own entry body exists.
 */
function Arriving({
  onChange,
}: {
  readonly onChange: (pending: boolean) => void;
}): ReactNode {
  const { pending } = useLinkStatus();

  useEffect(() => {
    onChange(pending);
  }, [pending, onChange]);

  return null;
}

export interface RunCardToggleProps {
  readonly href: string;
  readonly open: boolean;
  readonly className: string;
  /** Named for a reader who cannot see the chevron change. */
  readonly label: string;
  readonly children: ReactNode;
}

/** The card's header row, as the control that opens and closes it. */
export function RunCardToggle({
  href,
  open,
  className,
  label,
  children,
}: RunCardToggleProps): ReactNode {
  const [pending, setPending] = useState(false);
  const publish = useCallback((value: boolean) => {
    setPending(value);
  }, []);

  return (
    <NextLink
      href={href}
      scroll={false}
      prefetch={false}
      aria-expanded={open}
      aria-busy={pending}
      data-testid="run-card-toggle"
      data-pending={pending ? 'true' : 'false'}
      className={className}
      onClick={(event) => {
        if (pending) event.preventDefault();
      }}
    >
      <Arriving onChange={publish} />
      {children}
      <span className="shrink-0 text-muted" aria-hidden="true">
        {pending ? (
          <span
            data-testid="run-card-arriving"
            className="inline-block size-2 rounded-full bg-accent pulse-live"
          >
            <span className="pulse-live-ring" />
          </span>
        ) : open ? (
          <ChevronDownIcon />
        ) : (
          <ChevronRightIcon />
        )}
      </span>
      <span className="sr-only" data-testid="run-card-arriving-label">
        {pending ? label : ''}
      </span>
    </NextLink>
  );
}
