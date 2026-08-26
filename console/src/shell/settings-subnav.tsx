'use client';

import NextLink from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

import { cx } from '@/design/cx';
import type { MessageKey } from '@/i18n/en';
import { message, type Locale } from '@/i18n/messages';
import type { SettingsGroup, SettingsPageGroup } from './routes';

/**
 * The Settings hub's own navigation: the three groups, drawn as the sidebar
 * itself is — a rail above the documented breakpoint, a control that keeps
 * every page reachable without a second horizontal scrollbar below it.
 *
 * A `<select>` rather than a second drawer for the narrow case: the sidebar
 * already owns the one drawer this shell opens, and a nested navigation
 * inside it would be two navigations competing for the same panel. A native
 * control needs nothing else to stay usable at 320 pixels.
 */

const GROUP_LABEL: Readonly<Record<SettingsGroup, MessageKey>> = {
  organization: 'settings.group.organization',
  agent: 'settings.group.agent',
  data: 'settings.group.data',
};

function isCurrentPage(path: string, current: string): boolean {
  return current === path || current.startsWith(`${path}/`);
}

export interface SettingsSubnavProps {
  readonly groups: readonly SettingsPageGroup[];
  readonly locale: Locale;
}

/** The rail, at and above the documented breakpoint. */
export function SettingsSubnav({ groups, locale }: SettingsSubnavProps): ReactNode {
  const current = usePathname();
  return (
    <nav
      data-testid="settings-subnav"
      aria-label={message(locale, 'settings.subnav.label')}
      className="hidden md:flex w-sidebar shrink-0 flex-col bg-surface edge border-y-0 border-l-0 border-border py-3"
    >
      {groups.map((group) => (
        <div key={group.group} className="px-2 pb-3">
          <p className="px-2 pb-1 text-micro text-muted">
            {message(locale, GROUP_LABEL[group.group])}
          </p>
          <ul>
            {group.pages.map((page) => {
              const active = isCurrentPage(page.path, current);
              return (
                <li key={page.id}>
                  <NextLink
                    href={page.path}
                    prefetch={false}
                    data-testid="settings-nav-entry"
                    data-page={page.id}
                    aria-current={active ? 'page' : undefined}
                    className={cx(
                      'block mx-1 px-2 py-1 rounded-2 text-body motion-hover',
                      active
                        ? 'bg-accent-bg text-accent font-semibold'
                        : 'text-text hover:bg-hover',
                    )}
                  >
                    {message(locale, page.label)}
                  </NextLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/** The same navigation, collapsed to one control, below the breakpoint. */
export function MobileSettingsSubnav({
  groups,
  locale,
}: SettingsSubnavProps): ReactNode {
  const current = usePathname();
  const router = useRouter();
  return (
    <div className="md:hidden px-1 pb-4">
      <label className="sr-only" htmlFor="settings-subnav-mobile">
        {message(locale, 'settings.subnav.label')}
      </label>
      <select
        id="settings-subnav-mobile"
        data-testid="settings-subnav-mobile"
        value={current}
        onChange={(event) => {
          router.push(event.target.value);
        }}
        className="w-full rounded-3 bg-surface edge border-border px-3 py-2 text-body"
      >
        {groups.map((group) => (
          <optgroup key={group.group} label={message(locale, GROUP_LABEL[group.group])}>
            {group.pages.map((page) => (
              <option key={page.id} value={page.path}>
                {message(locale, page.label)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
