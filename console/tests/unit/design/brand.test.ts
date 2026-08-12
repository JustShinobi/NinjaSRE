import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { MARK_SMALL_PATH, WORDMARK } from '@/design/brand';
import { LOCALES } from '@/i18n/messages';
import { message } from '@/i18n/messages';

/**
 * The mark exists three times, and this is what stops that being three marks.
 *
 * It has to: the rail needs it inline, because a mark in an `<img>` cannot
 * inherit `currentColor` and would come out black on a dark theme. The public
 * file has to exist for everything outside this application. The favicon has to
 * state a colour, because a browser tab has no page to inherit from.
 *
 * Three copies of one geometry is exactly the shape of thing that drifts, so
 * the geometry is compared rather than trusted — the same reasoning the
 * Tailwind theme and the token table are held together with.
 */

/** Resolved from the runner's root: a DOM environment cannot read from a module URL. */
function read(path: string): string {
  return readFileSync(join(process.cwd(), path), 'utf8');
}

/** The `d` of the first path in an SVG, with its whitespace collapsed. */
function pathData(svg: string): string {
  const found = /\bd="([^"]+)"/.exec(svg);
  expect(found, 'the SVG declares no path').not.toBeNull();
  return (found?.[1] ?? '').replace(/\s+/g, ' ').trim();
}

describe('the mark', () => {
  it('is one geometry, wherever it is drawn', () => {
    const inline = MARK_SMALL_PATH.replace(/\s+/g, ' ').trim();

    expect(pathData(read('public/brand/mark-small.svg'))).toBe(inline);
    expect(pathData(read('src/app/icon.svg'))).toBe(inline);
  });

  it('carries no colour of its own, in the two places that inherit one', () => {
    // The favicon is the exception and says so: a browser tab has nothing to
    // inherit from. Everywhere else a literal would be a mark that ignores the
    // theme it was dropped into.
    for (const file of [
      'public/brand/mark.svg',
      'public/brand/mark-small.svg',
      'public/brand/emblem.svg',
    ]) {
      const svg = read(file);
      expect(svg, `${file} names a colour`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(svg, `${file} does not inherit`).toContain('currentColor');
    }
  });

  it('offers both cuts, and the small one is the rounder of the two', () => {
    // The most likely mistake is using the display cut at menu size, so the
    // two files have to actually differ.
    const main = pathData(read('public/brand/mark.svg'));
    const small = pathData(read('public/brand/mark-small.svg'));
    expect(main).not.toBe(small);
    // The small cut's hole is larger: 6.5 against 5.5.
    expect(small).toContain('A6.5 6.5');
    expect(main).toContain('A5.5 5.5');
  });
});

describe('the wordmark', () => {
  it('splits the name without inventing or losing a letter', () => {
    for (const locale of LOCALES) {
      expect(`${WORDMARK.name}${WORDMARK.discipline}`).toBe(
        message(locale, 'app.name'),
      );
    }
  });

  it('puts the accent on what the thing is, not on the proper noun', () => {
    expect(WORDMARK.name).toBe('Ninja');
    expect(WORDMARK.discipline).toBe('SRE');
  });
});
