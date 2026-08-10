import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { FirstRunScreen } from '@/surfaces/screens/first-run';

/** The guided setup. An area of the console, never something in front of it. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('first-run');
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return FirstRunScreen(await surfaceContext(await searchParams));
}
