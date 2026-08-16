import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { settingsPageMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { SchedulesDestinationsScreen } from '@/surfaces/settings/schedules-destinations';

const ID = 'settings-schedules-destinations';

export function generateMetadata(): Promise<Metadata> {
  return settingsPageMetadata(ID);
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return SchedulesDestinationsScreen(await surfaceContext(await searchParams));
}
