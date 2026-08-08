import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { RunsScreen } from '@/surfaces/screens/runs';

/** One area of the product. What it is, and what it is for, come from the manifest. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('runs');
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return RunsScreen(await surfaceContext(await searchParams));
}
