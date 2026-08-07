'use client';

import type { ReactNode } from 'react';
import { useId } from 'react';

import { Button } from '@/components/action';
import { cx } from '@/design/cx';
import { ChevronRightIcon } from '@/design/icons';

/**
 * The patterns with a keyboard contract.
 *
 * Each of these has a specification saying which keys do what, and the reason
 * to follow it exactly is that a keyboard user has learned it somewhere else.
 * A tab list where the arrow keys do nothing is not a slightly worse tab list;
 * it is a tab list that does not work.
 */

export interface Tab {
  readonly id: string;
  readonly label: string;
}

export interface TabsProps {
  readonly tabs: readonly Tab[];
  readonly selected: string;
  readonly onSelect: (id: string) => void;
  readonly label: string;
  readonly children?: ReactNode;
}

/**
 * A row of tabs, with roving focus.
 *
 * Only the selected tab is in the tab order; the arrow keys move between them
 * and wrap. That is the pattern, and the wrap matters — a keyboard user at the
 * last tab pressing right expects the first, not silence.
 */
export function Tabs({
  tabs,
  selected,
  onSelect,
  label,
  children,
}: TabsProps): ReactNode {
  const base = useId();

  function move(delta: number): void {
    const index = tabs.findIndex((tab) => tab.id === selected);
    const next = tabs[(index + delta + tabs.length) % tabs.length];
    if (next !== undefined) onSelect(next.id);
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        role="tablist"
        aria-label={label}
        className="flex gap-1 edge border-border border-t-0 border-x-0"
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight') {
            event.preventDefault();
            move(1);
          }
          if (event.key === 'ArrowLeft') {
            event.preventDefault();
            move(-1);
          }
        }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`${base}-${tab.id}`}
            aria-selected={tab.id === selected}
            // Only the selected tab names a panel, because only the selected
            // panel is in the tree. An unselected tab pointing at a panel that
            // does not exist is a dangling reference, which the pattern allows
            // precisely so that panels can be rendered one at a time.
            aria-controls={tab.id === selected ? `${base}-${tab.id}-panel` : undefined}
            tabIndex={tab.id === selected ? 0 : -1}
            onClick={() => {
              onSelect(tab.id);
            }}
            className={cx(
              'px-3 py-2 text-small motion-hover',
              tab.id === selected
                ? 'text-accent border-accent'
                : 'text-muted border-transparent',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`${base}-${selected}-panel`}
        aria-labelledby={`${base}-${selected}`}
        tabIndex={0}
      >
        {children}
      </div>
    </div>
  );
}

export interface Crumb {
  readonly label: string;
  readonly href?: string;
}

export interface BreadcrumbProps {
  readonly trail: readonly Crumb[];
}

/** Where this page sits, with the current page marked and not linked to itself. */
export function Breadcrumb({ trail }: BreadcrumbProps): ReactNode {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-2 text-meta text-muted">
        {trail.map((crumb, index) => (
          <li key={crumb.label} className="flex items-center gap-2">
            {crumb.href === undefined ? (
              <span aria-current="page" className="text-text">
                {crumb.label}
              </span>
            ) : (
              <a href={crumb.href} className="underline underline-offset-2">
                {crumb.label}
              </a>
            )}
            {index < trail.length - 1 ? <ChevronRightIcon /> : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export interface PaginationProps {
  readonly page: number;
  readonly pages: number;
  readonly onPage: (page: number) => void;
}

/**
 * Which page of a long list is showing.
 *
 * The control at the edge is disabled rather than hidden. Hiding it would move
 * everything beside it as the reader arrives at the first page, which is
 * movement under the pointer at the exact moment somebody is about to click.
 */
export function Pagination({ page, pages, onPage }: PaginationProps): ReactNode {
  return (
    <nav aria-label="Pagination" className="flex items-center gap-3">
      <Button
        state={page <= 1 ? 'disabled' : 'default'}
        onClick={() => {
          onPage(page - 1);
        }}
      >
        Previous
      </Button>
      <span className="text-meta text-muted tabular-nums">
        Page {page} of {pages}
      </span>
      <Button
        state={page >= pages ? 'disabled' : 'default'}
        onClick={() => {
          onPage(page + 1);
        }}
      >
        Next
      </Button>
    </nav>
  );
}

export interface AvatarProps {
  readonly name: string;
}

/** Initials, with the name they stand for available to anybody who cannot see them. */
export function Avatar({ name }: AvatarProps): ReactNode {
  const trimmed = name.trim();
  const initials =
    trimmed === ''
      ? '?'
      : trimmed
          .split(/\s+/)
          .slice(0, 2)
          .map((part) => part.charAt(0).toUpperCase())
          .join('');
  return (
    <span
      role="img"
      aria-label={trimmed === '' ? 'Unknown person' : trimmed}
      className="inline-flex items-center justify-center size-5 rounded-full bg-info-bg text-info text-meta"
    >
      {initials}
    </span>
  );
}
