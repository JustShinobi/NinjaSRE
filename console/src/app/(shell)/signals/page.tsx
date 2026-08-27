import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { legacyRedirectHref } from '@/shell/legacy-redirect';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { SignalsScreen } from '@/surfaces/screens/signals';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/** One area of the product. What it is, and what it is for, come from the manifest. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('signals');
}

/**
 * Retired by the hybrid navigation, with one exception: Intake carries on as
 * Alert intake and Destinations and Schedules both carry on as Schedules &
 * destinations, so every other variant of this address redirects — but
 * Continuous observation has no Settings page yet (none of the nine the
 * subnav lists replaces it), so `?tab=observation` keeps rendering this
 * screen exactly as it always has, and `emptiness.ts`'s `watchingCause` keeps
 * pointing here without a stop along the way.
 */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const params = await searchParams;
  if (params.tab === 'observation') {
    return SignalsScreen(await surfaceContext(params));
  }
  redirect(legacyRedirectHref('/signals', params) ?? '/settings/alert-intake');
}
