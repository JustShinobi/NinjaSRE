import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { message } from '@/i18n/messages';
import { deployment, documentTitle } from '@/shell/deployment';
import { requestLocale } from '@/shell/request';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { IncidentDetailScreen } from '@/surfaces/screens/incident-detail';

/** One incident, named in the tab as well as on the page. */
export async function generateMetadata({
  params,
}: {
  readonly params: Promise<{ readonly incidentId: string }>;
}): Promise<Metadata> {
  const { incidentId } = await params;
  const locale = await requestLocale();
  return {
    title: documentTitle(incidentId, deployment().name),
    description: message(locale, 'page.incidents.context'),
  };
}

export default async function Page({
  params,
  searchParams,
}: {
  readonly params: Promise<{ readonly incidentId: string }>;
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const { incidentId } = await params;
  return IncidentDetailScreen(await surfaceContext(await searchParams), incidentId);
}
