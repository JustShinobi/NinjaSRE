import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { settingsGroupsFor } from '@/shell/routes';
import { surfaceContext } from '@/surfaces/context';

/**
 * The Settings hub has no page of its own: it opens on the first page of the
 * first subnav group this viewer may reach — the same "first thing you are
 * offered" rule a wizard's own first unfinished step follows — so the
 * address in the bar always names the page actually on screen.
 *
 * Every role this platform declares reaches at least one Settings page
 * (config.read alone already reaches two, in Data), so the fallback to the
 * dashboard is a safety net rather than a path any real viewer takes.
 */
export default async function Page(): Promise<ReactNode> {
  const { viewer } = await surfaceContext();
  const first = settingsGroupsFor(viewer)[0]?.pages[0];
  redirect(first === undefined ? '/' : first.path);
}
