import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { deployment, documentTitle } from '@/shell/deployment';
import { requestCredential, requestLocale } from '@/shell/request';
import { message, type Locale } from '@/i18n/messages';
import { routeParam } from '@/shell/route-params';
import { authorised, read } from '@/surfaces/read';
import { subjectOf } from '@/surfaces/run-subject';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { RunDetailScreen } from '@/surfaces/screens/run-detail';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/**
 * One investigation.
 *
 * The tab has to distinguish this investigation from the other two the operator
 * has open, and a 32-character hex distinguishes it from nothing a person can
 * hold in their head. So the tab carries the run's own name — the same one
 * `run-subject.ts` computes for the header and the list column — falling back
 * to the identifier only when the read that would produce a name itself
 * failed, never when the name it produced is merely the trigger-and-id pair.
 *
 * A failed read is not an error here. Metadata that threw would take the page
 * down over a tab title, so the identifier stands and the page renders.
 */
export async function generateMetadata({
  params,
}: {
  readonly params: Promise<{ readonly runId: string }>;
}): Promise<Metadata> {
  const { runId: raw } = await params;
  const runId = routeParam(raw);
  const locale = await requestLocale();
  return {
    title: documentTitle(await tabTitle(runId, locale), deployment().name),
    description: message(locale, 'page.runs.context'),
  };
}

/** The run's own name, or its identifier when the read behind it failed. */
async function tabTitle(runId: string, locale: Locale): Promise<string> {
  const credential = await requestCredential();
  if (credential === null || credential === '') return runId;
  try {
    const detail = await read('/v1/runs/{run_id}', {
      ...authorised(credential),
      params: { run_id: runId },
    });
    return subjectOf(detail, locale).text;
  } catch {
    return runId;
  }
}

export default async function Page({
  params,
  searchParams,
}: {
  readonly params: Promise<{ readonly runId: string }>;
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  const { runId: raw } = await params;
  const runId = routeParam(raw);
  return RunDetailScreen(await surfaceContext(await searchParams), runId);
}
