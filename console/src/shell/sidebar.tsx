'use client';

import NextLink from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import { StatusDot } from '@/components/status';
import { Lockup } from '@/design/brand';
import { cx } from '@/design/cx';
import { message, type Locale, type MessageKey } from '@/i18n/messages';
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
 *
 * **The open area is read here, from the router, rather than handed in.** A
 * layout above these entries is not re-rendered by a segment navigation, so a
 * path passed down from one is captured on the first document and never moves
 * again — the entries keep pointing at wherever the tab was opened. The hook
 * is the only source that changes when a link is followed.
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

/** The noun in each badge's accessible name matches the count's meaning. */
const COUNT_LABEL: Readonly<Record<string, MessageKey>> = {
  decisions: 'nav.pending.decisions',
  incidents: 'nav.pending.incidents',
  runs: 'nav.pending.runs',
};

export interface SidebarProps {
  readonly viewer: Viewer;
  readonly locale: Locale;
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
  counts = {},
  checklistComplete = false,
  onNavigate,
}: Omit<SidebarProps, 'guardian'>): ReactNode {
  const current = usePathname();
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
                    //
                    // Prefetch is off rather than defaulted on: every area
                    // here is a dynamic Server Component that reads live,
                    // authenticated data on render, so a default prefetch
                    // would mean every one of the eighteen areas re-runs its
                    // API reads on every single navigation, not just the one
                    // the viewer opened — a stampede the gateway's session
                    // handling was not built to absorb.
                    prefetch={false}
                    data-testid="nav-entry"
                    data-area={area.id}
                    aria-current={current_ ? 'page' : undefined}
                    {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
                    className={cx(
                      'flex items-center gap-2 mx-1 px-2 py-1 rounded-2 text-body motion-hover',
                      current_
                        ? 'bg-accent-bg text-accent font-semibold'
                        : 'text-text hover:bg-hover',
                    )}
                  >
                    <Icon size="nav" />
                    <span className="truncate">{message(locale, area.label)}</span>
                    {count === undefined || count === 0 ? null : (
                      <span
                        data-testid="nav-count"
                        className="ml-auto rounded-full bg-danger-bg text-danger px-1 text-micro"
                        aria-label={message(
                          locale,
                          COUNT_LABEL[area.id] ?? 'nav.pending',
                          { count },
                        )}
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

/** Where the footer sends a reader who wants to know what the posture means. */
const AUTONOMY_PATH = '/autonomy';

/**
 * What the guardian is doing, in one line, always on screen.
 *
 * A link rather than a paragraph, because "propose-only" is jargon nobody
 * asked to learn — it is where this deployment's posture is explained *and*
 * controlled, so a reader who wants to know what it means and a reader who
 * wants to change it land in the same place.
 */
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
    <NextLink
      href={AUTONOMY_PATH}
      data-testid="guardian"
      data-live={guardian.live}
      data-posture={guardian.posture}
      title={message(locale, 'shell.guardian.tooltip')}
      className="mt-auto flex items-center gap-2 p-3 edge border-x-0 border-b-0 border-border text-meta text-muted hover:bg-hover motion-hover"
    >
      <StatusDot status={guardian.live ? 'healthy' : 'unknown'} />
      {message(locale, 'shell.guardian.state', {
        liveness,
        posture: message(locale, POSTURE_KEY[guardian.posture]),
      })}
    </NextLink>
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
      {/* p-4 is 16px, which clears the mark's own rule: nothing comes within
          half its height — 12px at this size — on any side, the container's
          own border included. */}
      <p className="p-4 edge border-x-0 border-t-0 border-border">
        <Lockup name={message(locale, 'app.name')} />
      </p>
      <SidebarNav
        viewer={viewer}
        locale={locale}
        checklistComplete={checklistComplete}
        {...(counts === undefined ? {} : { counts })}
      />
      <GuardianFooter locale={locale} guardian={guardian} />
    </nav>
  );
}
