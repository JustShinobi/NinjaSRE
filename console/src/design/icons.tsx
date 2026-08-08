import type { ReactNode } from 'react';

import { cx } from './cx';

/**
 * One outline set, drawn in this repository, imported one icon at a time.
 *
 * Drawn here rather than depended upon for the reason Article X gives: an icon
 * package is a dependency an operator has to audit, and an icon CDN is a
 * request that tells somebody else which page they opened. These are paths on a
 * 24-unit grid with a 2-unit stroke, inheriting `currentColor`, so an icon is
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

/** The frame every icon is drawn in. */
function Glyph({
  size = 'inline',
  className,
  title,
  children,
}: IconProps & { readonly children: ReactNode }): ReactNode {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
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
      <path d="M20 6 9 17l-5-5" />
    </Glyph>
  );
}

export function CloseIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M18 6 6 18M6 6l12 12" />
    </Glyph>
  );
}

export function PlusIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M12 5v14M5 12h14" />
    </Glyph>
  );
}

export function MinusIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M5 12h14" />
    </Glyph>
  );
}

export function ChevronRightIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="m9 18 6-6-6-6" />
    </Glyph>
  );
}

export function ChevronLeftIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="m15 18-6-6 6-6" />
    </Glyph>
  );
}

export function ChevronDownIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="m6 9 6 6 6-6" />
    </Glyph>
  );
}

export function AlertTriangleIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </Glyph>
  );
}

export function AlertCircleIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4M12 16h.01" />
    </Glyph>
  );
}

export function InfoIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 16v-4M12 8h.01" />
    </Glyph>
  );
}

export function ClockIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Glyph>
  );
}

export function SearchIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Glyph>
  );
}

export function RefreshIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M21 12a9 9 0 1 1-2.6-6.4" />
      <path d="M21 3v6h-6" />
    </Glyph>
  );
}

export function ServerIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <rect x="3" y="4" width="18" height="7" rx="1" />
      <rect x="3" y="13" width="18" height="7" rx="1" />
      <path d="M7 7.5h.01M7 16.5h.01" />
    </Glyph>
  );
}

export function DatabaseIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <ellipse cx="12" cy="5.5" rx="8" ry="3" />
      <path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13" />
      <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </Glyph>
  );
}

export function ActivityIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M3 12h4l3 8 4-16 3 8h4" />
    </Glyph>
  );
}

export function ShieldIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M12 3 4 6v6c0 5 3.4 8.3 8 9 4.6-.7 8-4 8-9V6l-8-3Z" />
    </Glyph>
  );
}

export function LayersIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 13 9 5 9-5" />
    </Glyph>
  );
}

export function SettingsIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" />
    </Glyph>
  );
}

export function BookIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v16H6.5A2.5 2.5 0 0 0 4 20.5V4.5Z" />
      <path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20v4H6.5A2.5 2.5 0 0 1 4 20.5Z" />
    </Glyph>
  );
}

export function ArrowRightIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M4 12h15M13 6l6 6-6 6" />
    </Glyph>
  );
}

export function CopyIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h8" />
    </Glyph>
  );
}

export function TrashIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M4 7h16M10 7V5h4v2M6 7l1 13h10l1-13" />
    </Glyph>
  );
}

export function InboxIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M3 13h5l1.5 3h5L16 13h5" />
      <path d="M5.5 5h13l2.5 8v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5l2.5-8Z" />
    </Glyph>
  );
}

/*
 * The shell's own shapes.
 *
 * Each of the eight below is drawn from the navigation the design reference
 * draws, on the same 24-unit grid at the same 2-unit stroke as the rest of the
 * set. They are here rather than in the shell because a shape used by one
 * surface today is used by three next month, and the second copy is the one
 * that is subtly different.
 */

/** The overview: four panels, which is what a dashboard is. */
export function GridIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </Glyph>
  );
}

/** A list: what a run log is before it is anything else. */
export function ListIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M4 6h16M4 12h16M4 18h10" />
    </Glyph>
  );
}

/** Two people: the administration of who may do what. */
export function UsersIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20a6 6 0 0 1 12 0M16 5.5a3 3 0 0 1 0 5M18 20a5 5 0 0 0-2-4" />
    </Glyph>
  );
}

/** Nodes and the edges between them. */
export function SitemapIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="19" r="2.5" />
      <circle cx="19" cy="19" r="2.5" />
      <path d="M12 7.5v4M10 13l-3.5 3.5M14 13l3.5 3.5" />
    </Glyph>
  );
}

/** What a past investigation left behind. */
export function BrainIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M12 3a4 4 0 0 0-4 4c-1.7.6-3 2.2-3 4a4 4 0 0 0 2 3.5V17a3 3 0 0 0 3 3h4a3 3 0 0 0 3-3v-2.5A4 4 0 0 0 19 11c0-1.8-1.3-3.4-3-4a4 4 0 0 0-4-4Z" />
    </Glyph>
  );
}

/** The record: a clipboard with rows on it. */
export function ClipboardIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-3" />
      <rect x="8" y="2" width="8" height="4" rx="1" />
      <path d="M8 11h8M8 15h5" />
    </Glyph>
  );
}

/** The notification centre, which is a bell whether or not it rings. */
export function BellIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 7-3 9h18c0-2-3-2-3-9Z" />
      <path d="M10 21h4" />
    </Glyph>
  );
}

/** The theme switch: a disc with rays, which is the same shape in both themes. */
export function ContrastIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2" />
    </Glyph>
  );
}

/** Lost, and a way back: a needle in a ring. */
export function CompassIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m15 9-2 5-4 1 2-5 4-1Z" />
    </Glyph>
  );
}

/** The drawer handle, which only exists below the breakpoint. */
export function MenuIcon(props: IconProps): ReactNode {
  return (
    <Glyph {...props}>
      <path d="M4 6h16M4 12h16M4 18h16" />
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
