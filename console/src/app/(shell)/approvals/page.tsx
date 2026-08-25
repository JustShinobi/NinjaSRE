import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { ApprovalsTab } from '@/surfaces/screens/approvals';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/** One area of the product. What it is, and what it is for, come from the manifest. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('approvals');
}

export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return ApprovalsTab(await surfaceContext(await searchParams));
}
