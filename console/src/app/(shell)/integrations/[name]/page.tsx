import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { routeParam } from '@/shell/route-params';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { IntegrationsScreen } from '@/surfaces/screens/integrations';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/**
 * The deep link into one integration's credential panel.
 *
 * Renders the identical catalogue `/integrations` does — same sections, same
 * filters, same grid — with the drawer for `name` already open, so a link
 * somebody was sent opens straight to the form rather than to the list they
 * would then have had to search again.
 */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('integrations');
}

export default async function Page({
  params,
  searchParams,
}: {
  readonly params: Promise<{ readonly name: string }>;
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const { name: raw } = await params;
  const name = routeParam(raw);
  return IntegrationsScreen(await surfaceContext(await searchParams), name);
}
