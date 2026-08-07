import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { tokenStylesheet } from '@/design/css';
import { NO_FLASH_SCRIPT } from '@/design/theme';

import './globals.css';

export const metadata: Metadata = {
  title: 'NinjaSRE',
  description: 'The NinjaSRE web console.',
};

/**
 * The document every screen is rendered into.
 *
 * Two things happen here that cannot happen anywhere else. The token stylesheet
 * is written into the head from the token table, so there is one source for the
 * values and no second copy to forget. And the theme override is applied by a
 * synchronous statement before the body exists — after that point any
 * correction is a frame of the wrong theme, which is what FR-004 forbids.
 *
 * The system default needs neither: it is a media query inside the same
 * stylesheet, so a viewer who has chosen nothing gets the right theme with no
 * JavaScript at all.
 */
export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>): ReactNode {
  return (
    <html lang="en">
      <head>
        <style
          data-testid="tokens"
          // The token table, rendered. Not user input and not reachable by one:
          // it is this repository's own module, evaluated on the server.
          dangerouslySetInnerHTML={{ __html: tokenStylesheet() }}
        />
        <script
          data-testid="no-flash"
          // Synchronous on purpose. A deferred script, or an effect, resolves
          // the theme after the first paint, which is the flash itself.
          dangerouslySetInnerHTML={{ __html: NO_FLASH_SCRIPT }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
