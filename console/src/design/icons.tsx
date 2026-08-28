import type { ReactNode } from 'react';

import { cx } from './cx';

/**
 * One outline set, drawn in this repository, imported one icon at a time.
 *
 * Drawn here rather than depended upon for the reason Article X gives: an icon
 * package is a dependency an operator has to audit, and an icon CDN is a
 * request that tells somebody else which page they opened. These are paths on
 * a 20-unit grid with a 1.6-unit stroke, round caps and round joins — the
 * design board's own drawing style — inheriting `currentColor`, so an icon is
 * whatever colour the thing around it is and no icon carries a colour of its
 * own.
 *
 * Each icon is a named export rather than an entry in a lookup table. That is
 * what makes the set tree-shakeable: a page that uses two icons carries two,
 * and a page that uses none carries none. A table would put all of them in
 * every bundle and the requirement would be satisfied only on paper.
 *
 * An icon is never the only carrier of meaning. It is decorative by default —
 * `aria-hidden`, no accessible name — and a control that shows nothing else has
 * to give one, which `IconButton` requires rather than suggests.
 *
 * This feature (the visual foundation) redrew every path below to the board's
 * grid and stroke; it renamed none of them and changed no export's props.
 * Where the board draws the same concept this set already had a name for, the
 * new path is the board's own coordinates; the rest keep their previous
 * silhouette, redrawn at the new grid and stroke. Two nav-icon assignments
 * moved to a better-fitting existing export instead of the board's exact
 * concept being drawn under a new name: `routes.ts`'s Incidents entry now
 * uses `ClockIcon` (the board draws a clock there) instead of
 * `AlertCircleIcon`, and its Decisions entry uses `ShieldIcon` (the board
 * draws a shield with a check inside) instead of `CheckIcon` — both were
 * already exported, already unused at that call site, and neither gained or
 * lost a signature. `console/tests/unit/design/icon-export-surface.test.tsx`
 * is the proof that this file's export surface — names, order, prop shape —
 * is unchanged by any of it.
 */

/** Where the icon sits, which is what decides how big it is. */
export type IconSize = 'inline' | 'nav' | 'head' | 'empty';

const SIZE_CLASS: Readonly<Record<IconSize, string>> = {
  inline: 'icon-inline',
  nav: 'icon-nav',
  head: 'icon-head',
  empty: 'icon-empty',
};

export interface IconProps {
  readonly size?: IconSize;
  readonly className?: string;
  /**
   * A name for an icon that is genuinely the only content.
   *
   * Almost always wrong: prefer a label beside the icon. It exists for the one
   * case where a shape *is* the information — a status glyph in a dense table.
   */
  readonly title?: string;
}

/** The frame every icon is drawn in — the board's own grid and stroke. */
function Glyph({
  size = 'inline',
  className,
  title,
  children,
}: IconProps & { readonly children: ReactNode }): ReactNode {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cx(SIZE_CLASS[size], 'shrink-0', className)}
      role={title === undefined ? 'presentation' : 'img'}
      aria-hidden={title === undefined ? true : undefined}
      aria-label={title}
    >
      {children}
    </svg>
  );
}

export function CheckIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M16.5 5 7.5 14 3.5 10" />
    </Glyph>
  );
}

export function CloseIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M15 5 5 15M5 5l10 10" />
    </Glyph>
  );
}

export function PlusIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M10 4.5v11M4.5 10h11" />
    </Glyph>
  );
}

export function MinusIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M4.5 10h11" />
    </Glyph>
  );
}

export function ChevronRightIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="m7.5 15 5-5-5-5" />
    </Glyph>
  );
}

export function ChevronLeftIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="m12.5 15-5-5 5-5" />
    </Glyph>
  );
}

export function ChevronDownIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="m5 7.5 5 5 5-5" />
    </Glyph>
  );
}

export function AlertTriangleIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M8.6 3.3 1.5 15a1.7 1.7 0 0 0 1.4 2.5h14.2a1.7 1.7 0 0 0 1.4-2.5L11.4 3.3a1.7 1.7 0 0 0-2.8 0Z" />
      <path d="M10 7.5v3.3M10 14.2h.01" />
    </Glyph>
  );
}

export function AlertCircleIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M10 6.7v3.3M10 13.3h.01" />
    </Glyph>
  );
}

export function InfoIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M10 13.3v-3.3M10 6.7h.01" />
    </Glyph>
  );
}

/** The board's own clock, drawn for the concept it names — "relógio de incidentes". */
export function ClockIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M10 6.2v4.2l2.6 1.6" />
    </Glyph>
  );
}

/** The board's own search lens — the topbar's search box and the "Investigações" nav entry. */
export function SearchIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="8.6" cy="8.6" r="5.6" />
      <path d="m13 13 4.4 4.4" />
    </Glyph>
  );
}

export function RefreshIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M17.5 10a7.5 7.5 0 1 1-2.2-5.3" />
      <path d="M17.5 2.5v5h-5" />
    </Glyph>
  );
}

/** The board's own server rack — "servidor de recursos". */
export function ServerIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <rect x="2.5" y="3" width="15" height="5.5" rx="1.5" />
      <rect x="2.5" y="11.5" width="15" height="5.5" rx="1.5" />
      <path d="M5.6 5.75h.01M5.6 14.25h.01" />
    </Glyph>
  );
}

export function DatabaseIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <ellipse cx="10" cy="4.6" rx="6.7" ry="2.5" />
      <path d="M3.3 4.6v10.8c0 1.4 3 2.5 6.7 2.5s6.7-1.1 6.7-2.5V4.6" />
      <path d="M3.3 10c0 1.4 3 2.5 6.7 2.5s6.7-1.1 6.7-2.5" />
    </Glyph>
  );
}

/** The board's own pulse line — "pulso do agente". */
export function ActivityIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M2.5 10h3l2-4.5 3 9 2-4.5h5" />
    </Glyph>
  );
}

/** The board's own shield with a check inside — "escudo de decisões". */
export function ShieldIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M10 2.5l6.5 3v4.7c0 4-2.8 6.6-6.5 7.8-3.7-1.2-6.5-3.8-6.5-7.8V5.5l6.5-3z" />
      <path d="M7.2 10l2 2 3.6-3.8" />
    </Glyph>
  );
}

export function LayersIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M7 3v4a3 3 0 0 0 6 0V3" />
      <path d="M10 10v3.5" />
      <path d="M6.5 17h7" />
      <path d="M10 13.5c-2 0-3.5 1.5-3.5 3.5h7c0-2-1.5-3.5-3.5-3.5z" />
    </Glyph>
  );
}

/** The board's own gear — "engrenagem de ajustes". */
export function SettingsIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="10" cy="10" r="2.6" />
      <path d="M10 2.8v2.2M10 15v2.2M2.8 10H5M15 10h2.2M4.9 4.9l1.6 1.6M13.5 13.5l1.6 1.6M15.1 4.9l-1.6 1.6M6.5 13.5l-1.6 1.6" />
    </Glyph>
  );
}

/** The board's own open book — "livro de conhecimento". */
export function BookIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M10 4.5c-1.6-1.4-3.8-1.6-6-1v12c2.2-.6 4.4-.4 6 1 1.6-1.4 3.8-1.6 6-1v-12c-2.2-.6-4.4-.4-6 1z" />
      <path d="M10 4.5v12" />
    </Glyph>
  );
}

export function ArrowRightIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M3.3 10h12.5M10.8 5l5 5-5 5" />
    </Glyph>
  );
}

export function CopyIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <rect x="7.5" y="7.5" width="10" height="10" rx="1.7" />
      <path d="M4.2 12.5V4.2a1.7 1.7 0 0 1 1.7-1.7h6.7" />
    </Glyph>
  );
}

export function TrashIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M3.3 5.8h13.3M8.3 5.8V4.2h3.3v1.7M5 5.8l.8 10.8h8.3l.8-10.8" />
    </Glyph>
  );
}

export function InboxIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M2.5 10.8h4.2l1.25 2.5h4.2l1.25-2.5h4.2" />
      <path d="M4.6 4.2h10.8l2.1 6.7v4.2a1.7 1.7 0 0 1-1.7 1.7H4.2a1.7 1.7 0 0 1-1.7-1.7v-4.2l2.1-6.7Z" />
    </Glyph>
  );
}

/*
 * The shell's own shapes.
 *
 * Each is drawn from the navigation the design board draws, on the same
 * 20-unit grid at the same 1.6-unit stroke as the rest of the set. They are
 * here rather than in the shell because a shape used by one surface today is
 * used by three next month, and the second copy is the one that is subtly
 * different.
 */

/** The board's own four-panel grid — "grade do painel". */
export function GridIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <rect x="2.5" y="2.5" width="6" height="6" rx="1.5" />
      <rect x="11.5" y="2.5" width="6" height="6" rx="1.5" />
      <rect x="2.5" y="11.5" width="6" height="6" rx="1.5" />
      <rect x="11.5" y="11.5" width="6" height="6" rx="1.5" />
    </Glyph>
  );
}

/** A list: rows, for wherever this console still needs one (the density toggle). */
export function ListIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M3.3 5h13.3M3.3 10h13.3M3.3 15h8.3" />
    </Glyph>
  );
}

/** Two people: the administration of who may do what. */
export function UsersIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="7.5" cy="6.7" r="2.5" />
      <path d="M2.5 16.7a5 5 0 0 1 10 0M13.3 4.6a2.5 2.5 0 0 1 0 4.2M15 16.7a4.2 4.2 0 0 0-1.7-3.3" />
    </Glyph>
  );
}

/** Nodes and the edges between them. */
export function SitemapIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="10" cy="4.2" r="2.1" />
      <circle cx="4.2" cy="15.8" r="2.1" />
      <circle cx="15.8" cy="15.8" r="2.1" />
      <path d="M10 6.3v3.3M8.3 10.8l-2.9 2.9M11.7 10.8l2.9 2.9" />
    </Glyph>
  );
}

/** What a past investigation left behind. */
export function BrainIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M10 2.5a3.3 3.3 0 0 0-3.3 3.3c-1.4.5-2.5 1.8-2.5 3.3a3.3 3.3 0 0 0 1.7 2.9v2.3a2.5 2.5 0 0 0 2.5 2.5h3.3a2.5 2.5 0 0 0 2.5-2.5v-2.1a3.3 3.3 0 0 0 1.7-2.9c0-1.5-1.1-2.8-2.5-3.3a3.3 3.3 0 0 0-3.4-3.3Z" />
    </Glyph>
  );
}

/** The record: a clipboard with rows on it. */
export function ClipboardIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M6.7 2.5H4.2a1.7 1.7 0 0 0-1.7 1.7v11.7a1.7 1.7 0 0 0 1.7 1.7h11.7a1.7 1.7 0 0 0 1.7-1.7V4.2a1.7 1.7 0 0 0-1.7-1.7h-2.5" />
      <rect x="6.7" y="1.7" width="6.7" height="3.3" rx=".8" />
      <path d="M6.7 9.2h6.7M6.7 12.5h4.2" />
    </Glyph>
  );
}

/** The board's own bell — "sino". */
export function BellIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M10 3a4.6 4.6 0 0 0-4.6 4.6c0 3.2-1.1 4.6-1.9 5.4h13c-.8-.8-1.9-2.2-1.9-5.4A4.6 4.6 0 0 0 10 3z" />
      <path d="M8.4 16a1.7 1.7 0 0 0 3.2 0" />
    </Glyph>
  );
}

/** The board's own theme disc with rays — "tema". */
export function ContrastIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="10" cy="10" r="3.4" />
      <path d="M10 2.6v1.8M10 15.6v1.8M2.6 10h1.8M15.6 10h1.8M4.8 4.8l1.3 1.3M13.9 13.9l1.3 1.3M15.2 4.8l-1.3 1.3M6.1 13.9l-1.3 1.3" />
    </Glyph>
  );
}

/** Lost, and a way back: a needle in a ring. */
export function CompassIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="m12.5 7.5-1.7 4.2-3.3.8 1.7-4.2 3.3-.8Z" />
    </Glyph>
  );
}

/** The drawer handle, which only exists below the breakpoint. */
export function MenuIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M3.3 5h13.3M3.3 10h13.3M3.3 15h13.3" />
    </Glyph>
  );
}

/** Every icon this set ships, for the gallery and for the coverage test. */
export const ICON_NAMES = [
  'CheckIcon',
  'CloseIcon',
  'PlusIcon',
  'MinusIcon',
  'ChevronRightIcon',
  'ChevronLeftIcon',
  'ChevronDownIcon',
  'AlertTriangleIcon',
  'AlertCircleIcon',
  'InfoIcon',
  'ClockIcon',
  'SearchIcon',
  'RefreshIcon',
  'ServerIcon',
  'DatabaseIcon',
  'ActivityIcon',
  'ShieldIcon',
  'LayersIcon',
  'SettingsIcon',
  'BookIcon',
  'ArrowRightIcon',
  'CopyIcon',
  'TrashIcon',
  'InboxIcon',
  'GridIcon',
  'ListIcon',
  'SitemapIcon',
  'UsersIcon',
  'BrainIcon',
  'ClipboardIcon',
  'BellIcon',
  'ContrastIcon',
  'CompassIcon',
  'MenuIcon',
] as const;
