import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { legacyRedirectHref } from '@/shell/legacy-redirect';
import type { SearchParams } from '@/surfaces/context';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/**
 * Retired: the sidebar and the search palette have called this area "Runs"
 * since the hybrid navigation, but `/investigations` is the name people
 * remember, share in a link, or type from habit — so it answers rather than
 * ending in the console's own "there is no such page". Every query
 * parameter rides along.
 */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const params = await searchParams;
  redirect(legacyRedirectHref('/investigations', params) ?? '/runs');
}
