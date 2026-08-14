'use client';

import { useState, type ReactNode } from 'react';

import { cx } from '@/design/cx';
import { ChevronDownIcon } from '@/design/icons';

/**
 * Reference content, out of the operator's way until it is asked for.
 *
 * A webhook payload, "not covered, and why", a conceptual explanation — the
 * design document is explicit that none of it belongs between an operator
 * and the form they came to fill in. This is the one shape that content
 * takes everywhere it appears: a title and a one-line summary, both visible
 * with nothing expanded, and everything else behind a single control. A
 * screen with reference content writes it once, here, rather than inventing
 * its own collapsed paragraph.
 */

export interface ReferenceProps {
  readonly title: string;
  /** The one line visible even when nothing is expanded. */
  readonly summary: string;
  readonly children: ReactNode;
  readonly className?: string;
}

/** A title and a summary always shown; the rest, one press away. */
export function Reference({
  title,
  summary,
  children,
  className,
}: ReferenceProps): ReactNode {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      data-testid="reference"
      data-expanded={expanded}
      className={cx('rounded-3 edge border-border bg-sunken', className)}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => {
          setExpanded((was) => !was);
        }}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-strong">{title}</span>
          <span className="block text-meta text-muted">{summary}</span>
        </span>
        <ChevronDownIcon className={cx('shrink-0', expanded ? 'rotate-180' : '')} />
      </button>
      {expanded ? (
        <div data-testid="reference-body" className="px-4 pb-4 text-small text-muted">
          {children}
        </div>
      ) : null}
    </div>
  );
}
