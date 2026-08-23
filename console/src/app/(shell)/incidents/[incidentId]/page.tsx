import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { message } from '@/i18n/messages';
import { deployment, documentTitle } from '@/shell/deployment';
import { requestCredential, requestLocale } from '@/shell/request';
import { routeParam } from '@/shell/route-params';
import { field, text } from '@/surfaces/read';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { incidentDetailFor, IncidentDetailScreen } from '@/surfaces/screens/incident-detail';

/**
 * One incident, named in the tab as well as on the page.
 *
 * Reads through the same memoized, per-request `incidentDetailFor` the page
 * body reads through, so the tab and the H1 always name the same thing from
 * the same read rather than a second fetch that could disagree with the
 * first. A failed read falls back to the deployment's own name — never the
 * identifier, in any circumstance.
 */
export async function generateMetadata({
  params,
}: {
  readonly params: Promise<{ readonly incidentId: string }>;
}): Promise<Metadata> {
  const { incidentId: raw } = await params;
  const incidentId = routeParam(raw);
  const locale = await requestLocale();
  const deploymentName = deployment().name;

  const credential = await requestCredential();
  let title = '';
  if (credential !== null && credential !== '') {
    try {
      const detail = await incidentDetailFor(credential, incidentId);
      title = text(field(detail, 'incident'), 'title');
    } catch {
      title = '';
    }
  }

  return {
    title: title === '' ? deploymentName : documentTitle(title, deploymentName),
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
  const { incidentId: raw } = await params;
  const incidentId = routeParam(raw);
  return IncidentDetailScreen(await surfaceContext(await searchParams), incidentId);
}
