import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { declaredNames, referencedNames, tokenStylesheet } from '@/design/css';
import { THEMES } from '@/design/tokens';

/**
 * The token table is the single input, and this is what stops that being a
 * slogan.
 *
 * Three consumers read the table: the runtime custom properties, the Tailwind
 * theme, and the contrast test. The contrast test imports it directly, so it
 * cannot drift. The other two are text, and text drifts — so the Tailwind theme
 * is compared against the table by name, in both directions. A utility that
 * points at a token nobody declares fails here; a token nobody exposed as a
 * utility fails here too, because a token no component can reach is a token
 * somebody will work around with a literal.
 */

// Resolved from the runner's root rather than from `import.meta.url`: the DOM
// environment rewrites a module's own URL to an http one, and a file cannot be
// read from that.
const GLOBALS = readFileSync(join(process.cwd(), 'src/app/globals.css'), 'utf8');

/** The `@theme` block Tailwind reads, and nothing around it. */
function tailwindTheme(): string {
  const opened = GLOBALS.indexOf('@theme');
  expect(opened, 'globals.css declares no @theme block').toBeGreaterThanOrEqual(0);
  const start = GLOBALS.indexOf('{', opened);
  let depth = 0;
  for (let index = start; index < GLOBALS.length; index += 1) {
    if (GLOBALS[index] === '{') depth += 1;
    if (GLOBALS[index] === '}') {
      depth -= 1;
      if (depth === 0) return GLOBALS.slice(start + 1, index);
    }
  }
  throw new Error('the @theme block is not closed');
}

describe('the runtime token stylesheet', () => {
  it('declares every theme, and every theme declares the same names', () => {
    const names = THEMES.map((theme) => [...declaredNames(theme)].sort());
    expect(names[0]).toEqual(names[1]);
    expect(names[0]?.length).toBeGreaterThan(30);
  });

  it('follows the operating system, and lets an explicit choice win in both directions', () => {
    const sheet = tokenStylesheet();
    expect(sheet).toContain('@media (prefers-color-scheme: dark)');
    // The guard is what makes an explicit `light` survive a dark operating
    // system: without it the media query would win on specificity order.
    expect(sheet).toContain(':root:not([data-theme="light"])');
    expect(sheet).toContain('[data-theme="dark"]');
    expect(sheet).toContain('[data-theme="light"]');
  });

  it('names no colour outside a token declaration', () => {
    const sheet = tokenStylesheet();
    for (const line of sheet.split('\n')) {
      const literal = /#[0-9a-fA-F]{3,8}\b/.exec(line);
      if (literal === null) continue;
      expect(line.trim(), 'a colour appears outside a token declaration').toMatch(
        /^--[a-z0-9-]+:/,
      );
    }
  });
});

describe('the Tailwind theme and the token table', () => {
  it('exposes every declared token as something a component can reach', () => {
    const declared = declaredNames('light');
    // The whole sheet, not only the `@theme` block: Tailwind has no theme
    // namespace for a border width, a duration or an icon size, so those three
    // are utilities of their own. Either way the token is reachable by name.
    const referenced = referencedNames(GLOBALS);
    const unreachable = [...declared].filter((name) => !referenced.has(name)).sort();

    expect(
      unreachable,
      'these tokens have no utility, so a component can only reach them with a literal',
    ).toEqual([]);
  });

  it('points at no token the table does not declare', () => {
    const declared = declaredNames('light');
    const invented = [...referencedNames(tailwindTheme())].filter(
      (name) => !declared.has(name),
    );

    expect(invented, 'the Tailwind theme references tokens nothing declares').toEqual(
      [],
    );
  });

  it('reads the tokens rather than restating them, so one edit changes both', () => {
    const literal = /#[0-9a-fA-F]{3,8}\b/.exec(tailwindTheme());
    expect(
      literal,
      'the Tailwind theme restates a colour instead of referencing it',
    ).toBeNull();
  });
});
