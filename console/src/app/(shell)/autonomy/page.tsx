import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import type { SearchParams } from '@/surfaces/context';

/**
 * Retired by the hybrid navigation: this screen now lives at its Settings
 * address, unconditionally — autonomy never had tabs to preserve.
 */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  await searchParams;
  redirect('/settings/autonomy-guardrails');
}
