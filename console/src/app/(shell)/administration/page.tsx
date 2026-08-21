import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { legacyRedirectHref } from '@/shell/legacy-redirect';
import type { SearchParams } from '@/surfaces/context';

/**
 * Retired by the hybrid navigation: People carries on as Members & roles,
 * Audit carries on as its own page. `?tab=` decides which, the same way it
 * decided which tab this screen showed; every other filter rides along.
 */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const params = await searchParams;
  redirect(legacyRedirectHref('/administration', params) ?? '/settings/members-roles');
}
