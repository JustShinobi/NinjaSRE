'use client';

import NextLink from 'next/link';
import type { ReactNode } from 'react';

import { StatusDot } from '@/components/status';
import { cx } from '@/design/cx';
import { message, type Locale } from '@/i18n/messages';
import type { Viewer } from '@/session/viewer';
import { groupsFor, type Area } from './routes';

/**
 * The persistent navigation: the areas, grouped, with the current one marked.
 *
 * Three things about it are load-bearing rather than decorative.
 *
 * **Every entry has a shape as well as a word.** A column of twelve labels is
 * read by reading; a column of twelve labelled icons is read by recognising, and
 * recognition is what somebody does at three in the morning.
 *
 * **An entry the viewer cannot use is absent.** Not dimmed, not disabled —
 * absent. A disabled entry still says the capability exists, still says
 * somebody else has it, and still ships whatever sits behind it.
 *
 * **The footer always says whether the guardian is alive and what posture it is
 * in.** It is the one fact that has to be on screen whatever page is open,
 * because "did anything act on its own while I was reading this" is not a
 * question that should require navigating anywhere.
 */

/** Whether the guardian is running, and what it is currently allowed to do. */
export interface Guardian {
  readonly live: boolean;
  readonly posture: 'propose' | 'act' | 'frozen';
}

const POSTURE_KEY = {
  propose: 'shell.guardian.posture.propose',
  act: 'shell.guardian.posture.act',
  frozen: 'shell.guardian.posture.frozen',
} as const;

export interface SidebarProps {
  readonly viewer: Viewer;
  readonly locale: Locale;
  /** The path currently open, so exactly one entry is marked current. */
  readonly current: string;
  readonly guardian: Guardian;
  /** Per-area counts — the badge the design draws on Incidents and Approvals. */
  readonly counts?: Readonly<Record<string, number>>;
  /**
   * Whether the deployment has finished setting itself up.
   *
   * The navigation asks because one entry is a *task* rather than a place: it
   * belongs in front of somebody until the checklist closes and nowhere
   * afterwards. Passed in rather than read here, because a navigation
   * component that made a request would make one per render.
   */
  readonly checklistComplete?: boolean;
  /** Set when the sidebar is being rendered inside the drawer. */
  readonly onNavigate?: () => void;
}

function isCurrent(area: Area, current: string): boolean {
  if (area.path === '/') {
    return current === '/';
  }
  return current === area.path || current.startsWith(`${area.path}/`);
}

/** The navigation itself, without the frame — shared by the rail and the drawer. */
export function SidebarNav({
  viewer,
  locale,
  current,
  counts = {},
  checklistComplete = false,
  onNavigate,
}: Omit<SidebarProps, 'guardian'>): ReactNode {
  return (
    <div className="flex-1 overflow-y-auto py-1">
      {groupsFor(viewer, { checklistComplete }).map((group) => (
        <div key={group.group} className="px-2 pt-3 pb-1">
          <p className="px-2 pb-1 text-micro uppercase text-muted">
            {message(locale, `nav.group.${group.group}`)}
          </p>
          <ul>
            {group.areas.map((area) => {
              const Icon = area.icon;
              const current_ = isCurrent(area, current);
              const count = counts[area.id];
              return (
                <li key={area.id}>
                  <NextLink
                    href={area.path}
                    // The router's own link, so moving between areas is a
                    // segment fetch rather than a document load: the frame the
                    // viewer is looking at is not rebuilt, and the scroll
                    // position of the list they came from survives the trip.
                    prefetch
                    data-testid="nav-entry"
                    data-area={area.id}
                    aria-current={current_ ? 'page' : undefined}
                    {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
                    className={cx(
                      'flex items-center gap-2 mx-1 px-2 py-1 rounded-2 text-body motion-hover',
                      current_
                        ? 'bg-accent-bg text-accent font-semibold'
                        : 'text-text hover:bg-sunken',
                    )}
                  >
                    <Icon size="nav" />
                    <span className="truncate">{message(locale, area.label)}</span>
                    {count === undefined || count === 0 ? null : (
                      <span
                        data-testid="nav-count"
                        className="ml-auto rounded-full bg-danger-bg text-danger px-1 text-micro"
                        aria-label={message(locale, 'nav.pending', { count })}
                      >
                        {count}
                      </span>
                    )}
                  </NextLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** What the guardian is doing, in one line, always on screen. */
export function GuardianFooter({
  locale,
  guardian,
}: {
  readonly locale: Locale;
  readonly guardian: Guardian;
}): ReactNode {
  const liveness = message(
    locale,
    guardian.live ? 'shell.guardian.active' : 'shell.guardian.silent',
  );
  return (
    <p
      data-testid="guardian"
      data-live={guardian.live}
      data-posture={guardian.posture}
      className="mt-auto flex items-center gap-2 p-3 edge border-x-0 border-b-0 border-border text-meta text-muted"
    >
      <StatusDot status={guardian.live ? 'healthy' : 'unknown'} />
      {message(locale, 'shell.guardian.state', {
        liveness,
        posture: message(locale, POSTURE_KEY[guardian.posture]),
      })}
    </p>
  );
}

/**
 * The rail, at and above the declared breakpoint.
 *
 * Hidden below it rather than narrowed: a sidebar squeezed to fit a phone is a
 * column of wrapped words that costs a third of the screen and answers nothing.
 * What replaces it is the same navigation in a drawer, which is why `SidebarNav`
 * is a component rather than markup inside this one.
 */
export function Sidebar({
  viewer,
  locale,
  current,
  guardian,
  counts,
  checklistComplete = false,
}: SidebarProps): ReactNode {
  return (
    <nav
      data-testid="sidebar"
      aria-label={message(locale, 'nav.label')}
      className="hidden md:flex w-sidebar shrink-0 flex-col bg-surface edge border-y-0 border-l-0 border-border"
    >
      <p className="flex items-center gap-2 p-4 edge border-x-0 border-t-0 border-border">
        <span
          aria-hidden="true"
          className="grid place-items-center size-5 rounded-2 bg-accent text-on-accent text-meta font-bold"
        >
          {message(locale, 'app.name').slice(0, 1)}
        </span>
        <span className="text-strong">{message(locale, 'app.name')}</span>
      </p>
      <SidebarNav
        viewer={viewer}
        locale={locale}
        current={current}
        checklistComplete={checklistComplete}
        {...(counts === undefined ? {} : { counts })}
      />
      <GuardianFooter locale={locale} guardian={guardian} />
    </nav>
  );
}
