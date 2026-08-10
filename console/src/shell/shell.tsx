'use client';

import type { ReactNode } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/action';
import { Drawer } from '@/components/overlay';
import { message, type Locale } from '@/i18n/messages';
import { sessionController, type SessionEnding } from '@/session/controller';
import { signInHref } from '@/session/cookies';
import { endSession } from '@/session/end';
import { sessionLife } from '@/session/expiry';
import type { Viewer } from '@/session/viewer';
import { InvestigateDrawer } from '@/live/investigate';
import { onResolved, withoutItem, type AttentionItem } from './attention';
import { useNow } from './browser';
import { commandsFor, type Command, type RecentRun } from './commands';
import type { Deployment } from './deployment';
import { ImpersonationBanner } from './impersonation';
import type { SetupState } from './load';
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
  readonly current: string;
  readonly guardian: Guardian;
  readonly attention: readonly AttentionItem[];
  readonly recentRuns: readonly RecentRun[];
  readonly counts?: Readonly<Record<string, number>>;
  /**
   * What the deployment says about its own setup.
   *
   * The frame reads it because two things in the frame depend on it: the
   * navigation entry that exists only while there is something left to do, and
   * the caveat the investigation drawer carries when nothing is connected.
   */
  readonly setup?: SetupState;
  /**
   * Whether every automated write is currently stopped.
   *
   * In the frame rather than on the autonomy screen, because a screen where
   * nothing is happening looks the same whether nothing needed doing or
   * everything is stopped — and that is true of every screen, not one of them.
   */
  readonly stopped?: boolean;
  /** When the session ends, as the server knows it. Absent means it does not say. */
  readonly expiresAt?: string | null;
  readonly children: ReactNode;
  /** Where a command sends the browser. Injected so the suite can watch it. */
  readonly navigate?: (href: string) => void;
}

function defaultNavigate(href: string): void {
  window.location.assign(href);
}

export function Shell({
  viewer,
  locale,
  deployment,
  current,
  guardian,
  attention,
  recentRuns,
  counts,
  setup = { checklistComplete: false, integrationsConfigured: true },
  stopped = false,
  expiresAt = null,
  children,
  navigate = defaultNavigate,
}: ShellProps): ReactNode {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [investigateOpen, setInvestigateOpen] = useState(false);
  const [waiting, setWaiting] = useState<readonly AttentionItem[]>(attention);
  const [ending, setEnding] = useState<SessionEnding | null>(null);
  const now = useNow();

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

  const life = sessionLife(expiresAt, now ?? new Date(0));

  return (
    <div className="flex min-h-screen flex-col bg-sunken">
      <ImpersonationBanner viewer={viewer} locale={locale} />
      {/* Above everything, including the navigation. A stop nobody notices is a
          stop that gets engaged twice. */}
      <KillSwitchBanner locale={locale} engaged={stopped} />
      <div className="flex flex-1 min-h-0">
        <Sidebar
          viewer={viewer}
          locale={locale}
          current={current}
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
          <main id="main" data-testid="main" className="flex-1 overflow-auto p-5">
            {children}
          </main>
        </div>
      </div>

      {/* Reachable from every screen, because the thing somebody is looking at
          when they decide to investigate is the reason they are investigating,
          and a navigation to a form loses it. */}
      <InvestigateDrawer
        open={investigateOpen}
        locale={locale}
        integrationsConfigured={setup.integrationsConfigured}
        onClose={() => {
          setInvestigateOpen(false);
        }}
        navigate={navigate}
      />

      <Palette
        open={paletteOpen}
        locale={locale}
        commands={commands}
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
              current={current}
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
