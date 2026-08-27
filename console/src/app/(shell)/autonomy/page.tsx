import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { searchFrom, type SearchParams } from '@/surfaces/context';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/**
 * Retired by the hybrid navigation: this screen now lives at its Settings
 * address, with every filter the old address carried riding along — the
 * scope node it always named, and now the tab the destination understands
 * natively. Unlike `/administration` and `/signals`, `tab` is not dropped
 * here: this address never had a competing meaning for it (it had no tabs
 * of its own at all), so a value it carries means exactly what the
 * destination's own tab means today.
 */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const query = searchFrom(await searchParams).toString();
  redirect(
    query === ''
      ? '/settings/autonomy-guardrails'
      : `/settings/autonomy-guardrails?${query}`,
  );
}
