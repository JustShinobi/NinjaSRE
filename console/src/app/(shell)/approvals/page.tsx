import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { ApprovalsTab } from '@/surfaces/screens/approvals';

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
