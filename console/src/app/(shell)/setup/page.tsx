import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { legacyRedirectHref } from '@/shell/legacy-redirect';
import type { SearchParams } from '@/surfaces/context';

/**
 * Retired: the guided first run lives at `/first-run`, but "setup" is the
 * word the product's own vocabulary uses for it — the dashboard's setup
 * card, the checklist itself — so `/setup` answers rather than ending in
 * the console's own "there is no such page". Every query parameter rides
 * along.
 */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const params = await searchParams;
  redirect(legacyRedirectHref('/setup', params) ?? '/first-run');
}
