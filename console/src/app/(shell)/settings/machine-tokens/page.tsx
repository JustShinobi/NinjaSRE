import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { settingsPageMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { MachineTokensScreen } from '@/surfaces/settings/machine-tokens';

const ID = 'settings-machine-tokens';

export function generateMetadata(): Promise<Metadata> {
  return settingsPageMetadata(ID);
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return MachineTokensScreen(await surfaceContext(await searchParams));
}
