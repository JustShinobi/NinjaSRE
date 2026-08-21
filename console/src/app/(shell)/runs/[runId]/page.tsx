import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { deployment, documentTitle } from '@/shell/deployment';
import { requestCredential, requestLocale } from '@/shell/request';
import { message, type Locale } from '@/i18n/messages';
import { readFailure } from '@/surfaces/failures';
import { authorised, read, text } from '@/surfaces/read';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
import { RunDetailScreen } from '@/surfaces/screens/run-detail';

/**
 * One investigation.
 *
 * The tab has to distinguish this investigation from the other two the operator
 * has open, and a 32-character hex distinguishes it from nothing a person can
 * hold in their head. So the tab carries the *subject* — which is what the list
 * now leads with, and what somebody actually recognises — falling back to the
 * identifier only when the deployment recorded no summary at all.
 *
 * The subject is read through the same translation the screen uses, so a run
 * that failed before it began puts a sentence in the tab rather than the
 * deployment's exception and the name of an environment variable.
 *
 * A failed read is not an error here. Metadata that threw would take the page
 * down over a tab title, so the identifier stands and the page renders.
 */
export async function generateMetadata({
  params,
}: {
  readonly params: Promise<{ readonly runId: string }>;
}): Promise<Metadata> {
  const { runId } = await params;
  const locale = await requestLocale();
  return {
    title: documentTitle(await subjectOf(runId, locale), deployment().name),
    description: message(locale, 'page.runs.context'),
  };
}

/** What this investigation is about, or its identifier when nothing says. */
async function subjectOf(runId: string, locale: Locale): Promise<string> {
  const credential = await requestCredential();
  if (credential === null || credential === '') return runId;
  try {
    const detail = await read('/v1/runs/{run_id}', {
      ...authorised(credential),
      params: { run_id: runId },
    });
    const said = readFailure(text(detail, 'summary'), locale);
    return said.title === '' ? runId : said.title;
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
  const { runId } = await params;
  return RunDetailScreen(await surfaceContext(await searchParams), runId);
}
