'use client';

import type { ReactNode } from 'react';
import { useId } from 'react';
import NextLink from 'next/link';

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

/**
 * One tab's box, shared by both rows below.
 *
 * The two components have two keyboard contracts and both are right, which is
 * why there are two of them. They do not have two appearances, and writing the
 * box out twice is how they got one: `TabLinks` carried `edge border-t-0
 * border-x-0`, so its selected tab painted `border-accent` as an underline,
 * and `Tabs` carried the colour with no width for it to land on — so the
 * console's mark for "you are here" was a rule under the tab on some screens
 * and a change of text colour on others, split along a distinction (is the
 * section in the address?) that a reader cannot see.
 */
const TAB_SHAPE = 'px-3 py-2 text-small motion-hover edge border-t-0 border-x-0';

/** The selected tab's underline and colour, or the quiet treatment. */
function tabSkin(selected: boolean): string {
  return selected ? 'text-accent border-accent' : 'text-muted border-transparent';
}

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
            className={cx(TAB_SHAPE, tabSkin(tab.id === selected))}
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

/** One section of a screen, and the address that shows it. */
export interface TabLink {
  readonly id: string;
  readonly label: string;
  readonly href: string;
}

export interface TabLinksProps {
  readonly tabs: readonly TabLink[];
  readonly selected: string;
  readonly label: string;
}

/**
 * The same row of tabs, as links, for a screen whose section is in its address.
 *
 * Two components rather than a prop on one, because the keyboard contracts are
 * different and both are right. `Tabs` owns its selection, so only the selected
 * tab is in the tab order and the arrow keys move between them. These are
 * links: every one is in the tab order, Enter follows, and the arrow keys are
 * the browser's. Giving links roving focus would be borrowing a pattern that
 * only makes sense when the widget owns the state.
 *
 * The reason to have it at all is `url-state.ts`: whatever a screen is showing
 * is in its address, so that a section can be sent to somebody. A tab holding
 * its selection in component state passes every test about tabs and fails the
 * one that matters at three in the morning.
 *
 * Each tab is the router's link, not a plain anchor. The address is the same
 * either way — copyable, and followed with JavaScript off — but a plain
 * anchor is a document navigation: the shell is torn down and rebuilt, and
 * every read it makes is made again. The router's link keeps the shell and
 * repeats none of its reads; what it fetches is the section alone, and on
 * staging that transition measures a few hundred milliseconds. What it does
 * *not* do is show a loading state: a change of `?tab=` re-renders the same
 * segment inside a transition, and `loading.tsx` appears only for a segment
 * that had nothing rendered yet, so the previous section stays on screen,
 * unchanged, until the next one commits. Prefetching is off, as it is on
 * every link here: a section is a full server render against the
 * deployment, and the tabs nobody opens must not cost one.
 */
export function TabLinks({ tabs, selected, label }: TabLinksProps): ReactNode {
  return (
    <nav aria-label={label} data-testid="tab-links">
      <ul className="flex gap-1 edge border-border border-t-0 border-x-0">
        {tabs.map((tab) => (
          <li key={tab.id}>
            <NextLink
              href={tab.href}
              prefetch={false}
              data-testid="tab-link"
              data-tab={tab.id}
              aria-current={tab.id === selected ? 'page' : undefined}
              className={cx('block', TAB_SHAPE, tabSkin(tab.id === selected))}
            >
              {tab.label}
            </NextLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** One choice in a segmented control, and the address it navigates to. */
export interface SegmentedOption {
  readonly id: string;
  readonly label: string;
  readonly href: string;
  /** Drawn before the label — a severity's shape, a state's mark. */
  readonly icon?: ReactNode;
}

export interface SegmentedLinksProps {
  readonly options: readonly SegmentedOption[];
  readonly selected: string;
  readonly label: string;
}

/**
 * A row of mutually exclusive choices, as links, none of them a `<select>`.
 *
 * Same reasoning as `TabLinks`: whichever choice is active belongs in the
 * address, not in component state, so a filtered view can be sent to a
 * colleague and reload to the same rows. Unlike a tab list this is not a
 * single-purpose landmark — a screen may show more than one segmented group
 * side by side (state, severity, view) — so it carries its own accessible
 * name rather than assuming `nav` is unique on the page.
 *
 * Each choice is the router's link with prefetching off, for the reason
 * `TabLinks` gives: a plain anchor is a document navigation, and a change of
 * filter must not tear the shell down and repeat its reads.
 */
export function SegmentedLinks({
  options,
  selected,
  label,
}: SegmentedLinksProps): ReactNode {
  return (
    <nav
      aria-label={label}
      data-testid="segmented"
      className="inline-flex items-center rounded-2 bg-sunken edge border-border p-1"
    >
      {options.map((option) => (
        <NextLink
          key={option.id}
          href={option.href}
          prefetch={false}
          data-testid="segmented-option"
          data-option={option.id}
          aria-current={option.id === selected ? 'true' : undefined}
          className={cx(
            'flex items-center gap-2 rounded-2 px-3 py-1 text-small font-medium motion-hover',
            option.id === selected
              ? 'bg-accent-bg text-accent'
              : 'text-muted hover:text-text',
          )}
        >
          {option.icon}
          {option.label}
        </NextLink>
      ))}
    </nav>
  );
}

export interface Crumb {
  readonly label: string;
  readonly href?: string;
}

export interface BreadcrumbProps {
  readonly trail: readonly Crumb[];
  /**
   * The landmark's name, in the viewer's language.
   *
   * A required prop rather than a literal here. Everything a viewer reads comes
   * from the message catalogue, and a component that named its own landmark
   * would be one string in one language that no completeness test can see.
   */
  readonly label: string;
}

/** Where this page sits, with the current page marked and not linked to itself. */
export function Breadcrumb({ trail, label }: BreadcrumbProps): ReactNode {
  return (
    <nav aria-label={label}>
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
  /** The landmark's name, the two controls' names, and the position, translated. */
  readonly labels: {
    readonly landmark: string;
    readonly previous: string;
    readonly next: string;
    readonly position: string;
  };
}

/**
 * Which page of a long list is showing.
 *
 * The control at the edge is disabled rather than hidden. Hiding it would move
 * everything beside it as the reader arrives at the first page, which is
 * movement under the pointer at the exact moment somebody is about to click.
 */
export function Pagination({
  page,
  pages,
  onPage,
  labels,
}: PaginationProps): ReactNode {
  return (
    <nav aria-label={labels.landmark} className="flex items-center gap-3">
      <Button
        state={page <= 1 ? 'disabled' : 'default'}
        onClick={() => {
          onPage(page - 1);
        }}
      >
        {labels.previous}
      </Button>
      <span className="text-meta text-muted tabular-nums">{labels.position}</span>
      <Button
        state={page >= pages ? 'disabled' : 'default'}
        onClick={() => {
          onPage(page + 1);
        }}
      >
        {labels.next}
      </Button>
    </nav>
  );
}

export interface AvatarProps {
  readonly name: string;
  /** What to call somebody whose name is missing, in the viewer's language. */
  readonly unknownLabel: string;
}

/** Initials, with the name they stand for available to anybody who cannot see them. */
export function Avatar({ name, unknownLabel }: AvatarProps): ReactNode {
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
      aria-label={trimmed === '' ? unknownLabel : trimmed}
      className="inline-flex items-center justify-center size-5 rounded-full bg-info-bg text-info text-meta"
    >
      {initials}
    </span>
  );
}
