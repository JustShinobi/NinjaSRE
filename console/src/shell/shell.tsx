'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/action';
import { Drawer } from '@/components/overlay';
import { message, type Locale } from '@/i18n/messages';
import { sessionController, type SessionEnding } from '@/session/controller';
import { signInHref } from '@/session/cookies';
import { endSession } from '@/session/end';
import { sessionLife } from '@/session/expiry';
import { may, type Viewer } from '@/session/viewer';
import { InvestigateLauncher } from '@/live/investigate';
import { onResolved, withoutItem, type AttentionItem } from './attention';
import { useNow } from './browser';
import {
  commandsFor,
  searchCommands,
  type Command,
  type RecentRun,
  type SearchAnswer,
} from './commands';
import { askDeployment } from './search-client';
import type { Deployment } from './deployment';
import { ImpersonationBanner } from './impersonation';
import type { LauncherBriefing, SetupState, Stoppage } from './load';
import { NotificationCentre } from './notifications';
import { isPaletteShortcut, Palette } from './palette';
import { GuardianFooter, Sidebar, SidebarNav, type Guardian } from './sidebar';
import { KillSwitchBanner } from './stop';
import { Topbar } from './topbar';

/**
 * The frame every screen sits in.
 *
 * A client component with the page passed in as `children`, which is what keeps
 * the two claims of NFR-001 and NFR-004 true at once: the page is rendered on
 * the server and streamed in, and the chrome is server-rendered markup that a
 * browser paints before any of this hydrates. A slow API delays the page and
 * never the frame, because the frame does not wait for anything.
 *
 * Everything stateful in the shell lives here rather than in the piece that
 * shows it — the palette, the drawer, the notification list, the session. That
 * is deliberate: an item resolved on a page has to disappear from the
 * notification centre, and it can only do that if one component owns the list.
 */

export interface ShellProps {
  readonly viewer: Viewer;
  readonly locale: Locale;
  readonly deployment: Deployment;
  readonly guardian: Guardian;
  readonly attention: readonly AttentionItem[];
  readonly recentRuns: readonly RecentRun[];
  readonly counts?: Readonly<Record<string, number>>;
  /**
   * What the deployment says about its own setup.
   *
   * The frame reads it because three things in the frame depend on it: the
   * navigation entry that exists only while there is something left to do,
   * the caveat the investigation drawer carries when nothing is connected,
   * and the harder caveat — which disables starting one at all — when this
   * process has no runtime to run it in.
   */
  readonly setup?: SetupState;
  /**
   * Whether every automated write is currently stopped, and who did it.
   *
   * In the frame rather than on the autonomy screen, because a screen where
   * nothing is happening looks the same whether nothing needed doing or
   * everything is stopped — and that is true of every screen, not one of them.
   */
  readonly stopped?: Stoppage;
  /** What the investigate launcher offers before anything is typed. */
  readonly launcher?: LauncherBriefing;
  /** When the session ends, as the server knows it. Absent means it does not say. */
  readonly expiresAt?: string | null;
  readonly children: ReactNode;
  /** Where a command sends the browser. Injected so the suite can watch it. */
  readonly navigate?: (href: string) => void;
  /**
   * How the deployment is asked what answers to a palette query.
   *
   * Injected so the suite can drive the palette without a network. The default
   * is the courier, because the session credential is an HTTP-only cookie the
   * browser cannot read and a `fetch` from here could not carry it.
   */
  readonly askSearch?: typeof askDeployment;
}

function defaultNavigate(href: string): void {
  window.location.assign(href);
}

export function Shell({
  viewer,
  locale,
  deployment,
  guardian,
  attention,
  recentRuns,
  counts,
  setup = {
    checklistComplete: false,
    integrationsConfigured: true,
    runtimeComposed: true,
  },
  stopped = { engaged: false, by: null, since: null },
  launcher = { teamName: '', recurring: null, unhealthy: 0 },
  expiresAt = null,
  children,
  navigate = defaultNavigate,
  askSearch = askDeployment,
}: ShellProps): ReactNode {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [investigateOpen, setInvestigateOpen] = useState(false);
  const [waiting, setWaiting] = useState<readonly AttentionItem[]>(attention);
  const [ending, setEnding] = useState<SessionEnding | null>(null);
  const now = useNow();

  // Read here rather than handed in: a layout is not re-rendered by a segment
  // navigation, so a path from one is the path the tab was opened at. Three
  // things depend on it being the path the viewer is actually looking at — the
  // marked area, where signing out returns them, and what staying signed in
  // reloads.
  const current = usePathname();

  // The session ends once, wherever the refusal came from. This is the listener
  // half of that: the controller collapses, and what a collapse *does* is here.
  useEffect(() => {
    sessionController.listen(setEnding);
  }, []);

  useEffect(() => {
    if (ending === null) return;
    navigate(signInHref(ending.returnTo, ending.reason));
  }, [ending, navigate]);

  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (isPaletteShortcut(event)) {
        event.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  const commands = useMemo(
    () =>
      commandsFor(viewer, locale, recentRuns, {
        checklistComplete: setup.checklistComplete,
      }),
    [viewer, locale, recentRuns, setup.checklistComplete],
  );

  // An item resolved on any surface leaves the list here, without a refresh and
  // without every intervening component knowing that a list exists.
  useEffect(
    () =>
      onResolved((id) => {
        setWaiting((items) => withoutItem(items, id));
      }),
    [],
  );

  const run = useCallback(
    (command: Command) => {
      setPaletteOpen(false);
      navigate(command.href);
    },
    [navigate],
  );

  // The permission filter is here rather than in the palette because this is
  // where the viewer is. It is the same rule the local commands go through, and
  // one place deciding it is what keeps a search from being the way somebody
  // reaches a screen the navigation would not have offered them.
  const search = useCallback(
    async (query: string, signal: AbortSignal): Promise<SearchAnswer> => {
      const answer = await askSearch(query, signal);
      return {
        commands: searchCommands(answer.found, locale).filter(
          (command) => command.permission === null || may(viewer, command.permission),
        ),
        partial: answer.partial,
      };
    },
    [askSearch, locale, viewer],
  );

  const life = sessionLife(expiresAt, now ?? new Date(0));

  return (
    <div className="flex min-h-screen flex-col bg-sunken">
      <ImpersonationBanner viewer={viewer} locale={locale} />
      {/* Above everything, including the navigation. A stop nobody notices is a
          stop that gets engaged twice. */}
      <KillSwitchBanner
        locale={locale}
        engaged={stopped.engaged}
        by={stopped.by}
        since={stopped.since}
        zone={deployment.timezone}
      />
      <div className="flex flex-1 min-h-0">
        <Sidebar
          viewer={viewer}
          locale={locale}
          guardian={guardian}
          checklistComplete={setup.checklistComplete}
          {...(counts === undefined ? {} : { counts })}
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar
            viewer={viewer}
            locale={locale}
            deployment={deployment}
            attention={waiting}
            onOpenPalette={() => {
              setPaletteOpen(true);
            }}
            onOpenNotifications={() => {
              setNotificationsOpen((was) => !was);
            }}
            onOpenDrawer={() => {
              setDrawerOpen(true);
            }}
            onInvestigate={() => {
              setInvestigateOpen(true);
            }}
            stopped={stopped}
            onSignOut={() => {
              // The server's session ends first. Navigating away with the
              // cookie still set is not signing out, it is closing a tab —
              // and the next person at that keyboard is still signed in.
              void endSession().then(() => {
                sessionController.signOut(current);
              });
            }}
          />
          <div className="relative">
            <NotificationCentre
              open={notificationsOpen}
              locale={locale}
              items={waiting}
              onClose={() => {
                setNotificationsOpen(false);
              }}
            />
          </div>
          {now !== null && life.phase === 'expiring' ? (
            <p
              data-testid="session-expiring"
              role="status"
              className="flex items-center gap-3 bg-warning-bg px-5 py-1 text-small text-warning"
            >
              {message(locale, 'session.expiring', {
                duration: String(Math.ceil(life.secondsLeft / 60)),
              })}
              <Button
                data-testid="stay-signed-in"
                onClick={() => {
                  navigate(current);
                }}
              >
                {message(locale, 'session.expiring.action')}
              </Button>
            </p>
          ) : null}
          {/* The scroll container is full-bleed and the measure sits inside it,
              so the scrollbar stays at the window's edge while the content stops
              at the width the tokens declare. `--width-page` had been served on
              `:root` since the tokens landed with nothing applying it: on a wide
              display `<main>` ran to 2247px, and what that cost was not tidiness
              — it was every row whose name and metadata were a head-turn apart,
              and every paragraph running past 900px. */}
          <main id="main" data-testid="main" className="flex-1 overflow-auto">
            <div data-testid="page-measure" className="mx-auto w-full max-w-page p-5">
              {children}
            </div>
          </main>
        </div>
      </div>

      {/* Reachable from every screen, because the thing somebody is looking at
          when they decide to investigate is the reason they are investigating,
          and a navigation to a form loses it. */}
      <InvestigateLauncher
        open={investigateOpen}
        locale={locale}
        integrationsConfigured={setup.integrationsConfigured}
        runtimeComposed={setup.runtimeComposed}
        briefing={launcher}
        deploymentName={deployment.name}
        posture={guardian.posture}
        onClose={() => {
          setInvestigateOpen(false);
        }}
        navigate={navigate}
      />

      <Palette
        open={paletteOpen}
        locale={locale}
        commands={commands}
        search={search}
        onClose={() => {
          setPaletteOpen(false);
        }}
        onRun={run}
      />

      {/* Positioned by the shell rather than by the primitive: a drawer is a
          drawer because of where it sits, and the overlay component is the same
          panel wherever a screen decides to put it. */}
      {drawerOpen ? (
        <div className="fixed inset-y-0 left-0 z-10 flex w-sidebar max-w-full flex-col overflow-y-auto">
          <Drawer
            open
            title={message(locale, 'nav.label')}
            closeLabel={message(locale, 'shell.close')}
            onClose={() => {
              setDrawerOpen(false);
            }}
          >
            <SidebarNav
              viewer={viewer}
              locale={locale}
              checklistComplete={setup.checklistComplete}
              {...(counts === undefined ? {} : { counts })}
              onNavigate={() => {
                setDrawerOpen(false);
              }}
            />
            <GuardianFooter locale={locale} guardian={guardian} />
          </Drawer>
        </div>
      ) : null}
    </div>
  );
}
