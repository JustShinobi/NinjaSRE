import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { IntegrationsScreen } from '@/surfaces/screens/integrations';

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
  const { name } = await params;
  return IntegrationsScreen(await surfaceContext(await searchParams), name);
}
