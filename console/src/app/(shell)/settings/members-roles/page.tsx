import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { SettingsPageHeader, settingsPageMetadata } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { PeopleTab } from '@/surfaces/screens/administration';

const ID = 'settings-members-roles';

export function generateMetadata(): Promise<Metadata> {
  return settingsPageMetadata(ID);
}

/** The current tela equivalente: Administration's own People tab, unchanged. */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const context = await surfaceContext(await searchParams);
  return (
    <>
      <SettingsPageHeader page={settingsPageFor(ID)} locale={context.locale} />
      {await PeopleTab(context)}
    </>
  );
}
