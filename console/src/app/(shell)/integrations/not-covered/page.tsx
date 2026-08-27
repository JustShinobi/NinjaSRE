import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { NotCoveredScreen } from '@/surfaces/screens/not-covered';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/** The catalogue's reference page: every vendor it does not cover, and why. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('integrations-not-covered');
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return NotCoveredScreen(await surfaceContext(await searchParams));
}
