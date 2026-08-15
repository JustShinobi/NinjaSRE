import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { settingsPageMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { ModelsSettingsScreen } from '@/surfaces/settings/models';

const ID = 'settings-models-providers';

export function generateMetadata(): Promise<Metadata> {
  return settingsPageMetadata(ID);
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return ModelsSettingsScreen(await surfaceContext(await searchParams));
}
