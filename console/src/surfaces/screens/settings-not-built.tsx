import type { ReactNode } from 'react';

import { EmptyState } from '@/components/state';
import type { MessageKey } from '@/i18n/en';
import { message } from '@/i18n/messages';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor, type SettingsGroup } from '@/shell/routes';
import type { SurfaceContext } from '../context';

/**
 * The honest stand-in for a Settings page nothing has built yet.
 *
 * The shared `EmptyState` says three things by construction: what would
 * be here, why it is not, and what to do about it. Here "what to do" is the
 * only truthful answer there is before the page that owns this domain
 * ships — go back to the pages that already exist — which is also why this
 * never uses `resolveCta`: that helper validates against the route manifest
 * of top-level areas, and `/settings` is exactly that, an area, so a plain
 * link is both simpler and correct.
 */

const GROUP_LABEL: Readonly<Record<SettingsGroup, MessageKey>> = {
  organization: 'settings.group.organization',
  agent: 'settings.group.agent',
  data: 'settings.group.data',
};

/** The page named `id`, rendered as not built yet. */
export function NotBuiltSettingsPage(id: string, context: SurfaceContext): ReactNode {
  const { locale } = context;
  const page = settingsPageFor(id);
  return (
    <>
      <SettingsPageHeader page={page} locale={locale} />
      <EmptyState
        heading={message(locale, page.label)}
        body={message(locale, 'settings.notBuilt.body', {
          group: message(locale, GROUP_LABEL[page.group]),
        })}
        action={{
          label: message(locale, 'settings.notBuilt.action'),
          href: '/settings',
        }}
      />
    </>
  );
}
