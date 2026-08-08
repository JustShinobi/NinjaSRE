import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { DashboardScreen } from '@/surfaces/screens/dashboard';

/** The screen an operator lands on. What it is for comes from the manifest. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('dashboard');
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return DashboardScreen(await surfaceContext(await searchParams));
}
