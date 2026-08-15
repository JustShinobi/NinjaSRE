import type { ReactNode } from 'react';

import { EmptyState } from '@/components/state';
import type { MessageKey } from '@/i18n/en';
import { message } from '@/i18n/messages';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor, type SettingsGroup } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { readSetupState } from '../emptiness';
import { requestedSetupReturn, SetupReturnBanner } from '../first-run/return-banner';

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

/**
 * The page named `id`, rendered as not built yet.
 *
 * Async solely for the setup wizard's own handover: its last step points
 * here until the domain that owns this page ships, and while it does, this
 * is the one place that has to say "the guided setup sent you here, and it
 * is not finished" — read independently of the rest of the page, so a
 * failure to read the checklist degrades to no banner rather than to a
 * broken page.
 */
export async function NotBuiltSettingsPage(
  id: string,
  context: SurfaceContext,
): Promise<ReactNode> {
  const { credential, locale, search } = context;
  const page = settingsPageFor(id);
  const setup = await readSetupState(credential);
  return (
    <>
      <SettingsPageHeader page={page} locale={locale} />
      <SetupReturnBanner
        locale={locale}
        setup={setup}
        requested={requestedSetupReturn(search.get('return'))}
      />
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
