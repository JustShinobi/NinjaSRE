import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { deployment, documentTitle } from '@/shell/deployment';
import { requestLocale } from '@/shell/request';
import { message } from '@/i18n/messages';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { RunDetailScreen } from '@/surfaces/screens/run-detail';

/**
 * One run.
 *
 * The identifier is in the title as well as on the page: an operator with three
 * runs open has three tabs, and a tab that says only "Investigations" is a tab
 * they read the wrong run in.
 */
export async function generateMetadata({
  params,
}: {
  readonly params: Promise<{ readonly runId: string }>;
}): Promise<Metadata> {
  const { runId } = await params;
  const locale = await requestLocale();
  return {
    title: documentTitle(runId, deployment().name),
    description: message(locale, 'page.runs.context'),
  };
}

export default async function Page({
  params,
  searchParams,
}: {
  readonly params: Promise<{ readonly runId: string }>;
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const { runId } = await params;
  return RunDetailScreen(await surfaceContext(await searchParams), runId);
}
