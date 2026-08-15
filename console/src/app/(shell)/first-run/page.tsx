import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { areaMetadata } from '@/shell/area';
import { loadSetup } from '@/shell/load';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { FirstRunScreen } from '@/surfaces/screens/first-run';

/** The guided setup. An area of the console, never something in front of it. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('first-run');
}

/**
 * The wizard sits inside the shell like every other route, not in front of
 * it — the hybrid navigation only took its sidebar entry away, and the
 * sidebar's own invite (`SetupHero`, on the dashboard) is where the checklist
 * is offered now. This address still resolves: with the checklist finished,
 * it hands the operator back to the dashboard rather than showing the last
 * step of a wizard nothing is left to do in.
 */
export default async function Page({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const context = await surfaceContext(await searchParams);
  const setup = await loadSetup(context.credential);
  if (setup.checklistComplete) {
    redirect('/');
  }
  return FirstRunScreen(context);
}
