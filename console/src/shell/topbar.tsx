'use client';

import type { ReactNode } from 'react';

import { Button, IconButton } from '@/components/action';
import { Avatar } from '@/components/navigation';
import { BellIcon, ContrastIcon, MenuIcon, PlusIcon, SearchIcon } from '@/design/icons';
import { applyTheme, storeTheme } from '@/design/theme';
import type { Theme } from '@/design/tokens';
import { message, type Locale } from '@/i18n/messages';
import { may, type Viewer } from '@/session/viewer';
import type { AttentionItem } from './attention';
import { useChosenTheme } from './browser';
import type { Deployment } from './deployment';

/**
 * The utility bar: what deployment this is, the palette, the theme, what is
 * waiting, and who you are.
 *
 * Everything here is present for every viewer except the two controls that
 * change something — starting an investigation, and acting as somebody else.
 * Those follow the same rule the navigation does: absent rather than disabled,
 * because a control that exists and refuses is a control that has told a reader
 * what this deployment can do and who else can do it.
 */

export interface TopbarProps {
  readonly viewer: Viewer;
  readonly locale: Locale;
  readonly deployment: Deployment;
  readonly attention: readonly AttentionItem[];
  readonly onOpenPalette: () => void;
  readonly onOpenNotifications: () => void;
  readonly onOpenDrawer: () => void;
  /** Open the drawer that starts an investigation, from wherever this is. */
  readonly onInvestigate: () => void;
  readonly onSignOut: () => void;
}

/** The three theme choices, of which one is "stop overriding". */
const THEME_ORDER: readonly (Theme | null)[] = ['light', 'dark', null];

export function Topbar({
  viewer,
  locale,
  deployment,
  attention,
  onOpenPalette,
  onOpenNotifications,
  onOpenDrawer,
  onInvestigate,
  onSignOut,
}: TopbarProps): ReactNode {
  // The stored choice lives in the browser, and the server has no answer for
  // it. A store gives React a server snapshot and a client snapshot, so the
  // control is never rendered once with a guess and once with the truth.
  const chosen = useChosenTheme();

  function cycleTheme(): void {
    const index = THEME_ORDER.indexOf(chosen);
    const next = THEME_ORDER[(index + 1) % THEME_ORDER.length] ?? null;
    storeTheme(next);
    applyTheme(next);
  }

  const waiting = attention.length;

  return (
    <header
      data-testid="topbar"
      className="flex h-topbar shrink-0 items-center gap-2 px-3 md:gap-3 md:px-5 bg-surface edge border-x-0 border-t-0 border-border"
    >
      <span className="md:hidden">
        <IconButton
          label={message(locale, 'nav.open')}
          icon={<MenuIcon />}
          onClick={onOpenDrawer}
          data-testid="open-drawer"
        />
      </span>

      <button
        type="button"
        data-testid="open-palette"
        onClick={onOpenPalette}
        className="flex min-w-0 flex-1 max-w-prose items-center gap-2 rounded-2 edge border-border bg-sunken px-3 py-1 text-small text-muted"
      >
        <SearchIcon />
        <span className="truncate">{message(locale, 'shell.search')}</span>
        <kbd className="ml-auto rounded-1 edge border-border px-1 font-mono text-micro">
          {message(locale, 'shell.search.shortcut')}
        </kbd>
      </button>

      <span
        data-testid="deployment-name"
        className="ml-auto hidden truncate text-meta text-muted md:inline"
      >
        {deployment.name}
      </span>

      <span className="hidden sm:inline-flex">
        <IconButton
          label={message(locale, 'shell.theme')}
          icon={<ContrastIcon />}
          onClick={cycleTheme}
          data-testid="theme-switch"
          data-theme-choice={chosen ?? 'system'}
        />
      </span>

      <span className="relative inline-flex">
        <IconButton
          label={message(locale, 'notifications.open')}
          icon={<BellIcon />}
          onClick={onOpenNotifications}
          data-testid="open-notifications"
        />
        {waiting === 0 ? null : (
          <span
            data-testid="unread-count"
            aria-label={message(locale, 'notifications.unread', { count: waiting })}
            className="absolute top-0 right-0 rounded-full bg-danger px-1 text-micro text-on-danger"
          >
            {waiting}
          </span>
        )}
      </span>

      {may(viewer, 'investigation.run') ? (
        <Button variant="primary" data-testid="investigate" onClick={onInvestigate}>
          <PlusIcon />
          {/* The label goes below the breakpoint and the shape stays. The
              control keeps its accessible name either way, so nothing is lost
              to anybody who cannot see the icon. */}
          <span className="sr-only md:not-sr-only">
            {message(locale, 'shell.investigate')}
          </span>
        </Button>
      ) : null}

      <details className="relative" data-testid="account">
        <summary
          className="list-none marker:content-none"
          aria-label={message(locale, 'shell.account')}
        >
          <Avatar
            name={viewer.displayName}
            unknownLabel={message(locale, 'avatar.unknown')}
          />
        </summary>
        <div className="absolute right-0 z-10 mt-1 flex w-max flex-col gap-1 rounded-3 edge border-border bg-raised p-3 shadow-2">
          <span className="text-meta text-muted">{viewer.displayName}</span>
          {may(viewer, 'impersonation.use') ? (
            <Button data-testid="impersonate">
              {message(locale, 'shell.account.impersonate')}
            </Button>
          ) : null}
          <Button onClick={onSignOut} data-testid="sign-out">
            {message(locale, 'shell.account.signOut')}
          </Button>
        </div>
      </details>
    </header>
  );
}
