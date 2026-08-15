import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { settingsPageMetadata } from '@/shell/area';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { AutonomyScreen } from '@/surfaces/settings/autonomy';

export function generateMetadata(): Promise<Metadata> {
  return settingsPageMetadata('settings-autonomy-guardrails');
}

/**
 * Autonomy & guardrails: the single surface that edits what this deployment
 * may do on its own, at its Settings address.
 */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return AutonomyScreen(await surfaceContext(await searchParams));
}
