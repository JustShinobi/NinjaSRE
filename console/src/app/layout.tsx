import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { tokenStylesheet } from '@/design/css';
import { NO_FLASH_DENSITY_SCRIPT } from '@/design/density';
import { NO_FLASH_SCRIPT } from '@/design/theme';

import './globals.css';

export const metadata: Metadata = {
  title: 'NinjaSRE',
  description: 'The NinjaSRE web console.',
};

/**
 * The four woff2 files that paint above the fold on a cold cache: the
 * display family at the weight a page's H1 and a KPI figure use, the body
 * family at its two most common weights, and the mono family at its one
 * ordinary weight. The other four weights this console ships (display-500,
 * display-600, sans-600, mono-500) are asked for only where something on the
 * page actually needs them, so they load when the browser meets that
 * element rather than racing the four above for bandwidth on every load.
 */
const PRELOADED_FONTS = [
  '/fonts/space-grotesk-700.woff2',
  '/fonts/ibm-plex-sans-400.woff2',
  '/fonts/ibm-plex-sans-500.woff2',
  '/fonts/ibm-plex-mono-400.woff2',
] as const;

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
        <script
          data-testid="no-flash-density"
          // The same reasoning, and a worse symptom: a density corrected after
          // the paint is every row on the page changing height, which moves
          // whatever the viewer was about to click.
          dangerouslySetInnerHTML={{ __html: NO_FLASH_DENSITY_SCRIPT }}
        />
        {PRELOADED_FONTS.map((href) => (
          <link
            key={href}
            rel="preload"
            as="font"
            type="font/woff2"
            href={href}
            crossOrigin="anonymous"
          />
        ))}
      </head>
      <body>{children}</body>
    </html>
  );
}
