import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { settingsPageMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { NotificationsSettingsScreen } from '@/surfaces/settings/notifications';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

const ID = 'settings-notifications';

export function generateMetadata(): Promise<Metadata> {
  return settingsPageMetadata(ID);
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return NotificationsSettingsScreen(await surfaceContext(await searchParams));
}
