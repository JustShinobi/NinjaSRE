import type { ReactNode } from 'react';

import { settingsGroupsFor } from '@/shell/routes';
import { MobileSettingsSubnav, SettingsSubnav } from '@/shell/settings-subnav';
import { surfaceContext } from '@/surfaces/context';

/**
 * Every Settings page's own frame: the subnav, grouped by intention, next to
 * whichever page is open.
 *
 * The subnav reads the viewer itself rather than taking it from the page
 * below, for the reason `Shell`'s own layout resolves its viewer independently:
 * a client-side transition between two Settings pages fetches the page
 * segment alone, and a layout not re-rendered by that navigation would freeze
 * the subnav's own idea of who is looking at the moment the tab was opened.
 */
export default async function SettingsLayout({
  children,
}: Readonly<{ children: ReactNode }>): Promise<ReactNode> {
  const { viewer, locale } = await surfaceContext();
  const groups = settingsGroupsFor(viewer);

  return (
    <div className="flex gap-5">
      <SettingsSubnav groups={groups} locale={locale} />
      <div className="min-w-0 flex-1">
        <MobileSettingsSubnav groups={groups} locale={locale} />
        {children}
      </div>
    </div>
  );
}
