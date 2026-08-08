import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { EmptyStateLink } from '@/shell/empty-link';
import { message } from '@/i18n/messages';
import { deployment, documentTitle } from '@/shell/deployment';
import { requestLocale } from '@/shell/request';

/**
 * An address that names no area, answered inside the shell.
 *
 * Inside rather than instead of: the sidebar, the utility bar and the palette
 * are all still there, so the way back is the navigation somebody already knows
 * rather than the browser's back button. A bare not-found page would make a
 * mistyped URL feel like the console had fallen over.
 */
export async function generateMetadata(): Promise<Metadata> {
  const locale = await requestLocale();
  return {
    title: documentTitle(message(locale, 'notFound.title'), deployment().name),
  };
}

export default async function NotFound(): Promise<ReactNode> {
  const locale = await requestLocale();
  return (
    <div data-testid="not-found">
      <EmptyStateLink
        heading={message(locale, 'notFound.title')}
        body={message(locale, 'notFound.context')}
        actionLabel={message(locale, 'notFound.action')}
        href="/"
      />
    </div>
  );
}
