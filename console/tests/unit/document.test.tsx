import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RootLayout from '@/app/layout';
import { tokenStylesheet } from '@/design/css';
import { NO_FLASH_SCRIPT, THEME_ATTRIBUTE } from '@/design/theme';

/**
 * The document itself, rendered the way a server renders it.
 *
 * `renderToStaticMarkup` rather than a DOM render, because what is being
 * asserted is the *order of the head* — the token stylesheet and the theme
 * script have to be there before the body, and a DOM render into a `div` would
 * throw that away along with the `html` element it is about.
 */

const markup = renderToStaticMarkup(
  <RootLayout>
    <p>content</p>
  </RootLayout>,
);

describe('the document', () => {
  it('carries the token stylesheet rendered from the table', () => {
    expect(markup).toContain(tokenStylesheet().split('\n')[1]);
    expect(markup).toContain('--surface');
  });

  it('applies the theme override before the body exists', () => {
    const head = markup.slice(0, markup.indexOf('<body'));

    expect(head).toContain(NO_FLASH_SCRIPT);
    expect(head).toContain(THEME_ATTRIBUTE);
  });

  it('loads the theme script synchronously, because a deferred one is the flash', () => {
    const script = /<script[^>]*>/.exec(markup);

    expect(script).not.toBeNull();
    expect(script?.[0]).not.toContain('defer');
    expect(script?.[0]).not.toContain('async');
  });

  it('declares a language, which every assistive technology reads first', () => {
    expect(markup).toContain('<html lang="en">');
  });
});
