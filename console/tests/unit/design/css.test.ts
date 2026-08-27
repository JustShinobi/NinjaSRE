import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { declaredNames, referencedNames, tokenStylesheet } from '@/design/css';
import { COLOUR_ROLES, THEMES } from '@/design/tokens';

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

describe('the colours the source actually asks for', () => {
  /**
   * The direction the two checks above do not cover, and where four defects sat.
   *
   * Those hold the token table against the Tailwind theme. Neither of them
   * reads a component, so a component naming a colour role that does not exist
   * passes both — and Tailwind emits nothing at all for such a utility, which
   * is the quietest possible failure. It is not a wrong colour a reviewer might
   * query; it is no declaration, so the element keeps whatever it inherited.
   *
   * Four were shipped. `bg-subtle` on the change ruler's track left the track
   * invisible, so the marks along it floated on the panel. `bg-surface-sunken`,
   * in three places, left a preformatted block with no ground under it. And
   * `border-subtle` left a fieldset's rule painted in `currentColor` — the body
   * text colour — where every other rule on the screen is `border`.
   *
   * The lint rule cannot catch these: it rejects a colour *literal*, and these
   * are not literals. They are names, and the only thing that knows which names
   * exist is the token table. So this is the check that reads both.
   */
  const SOURCE = join(process.cwd(), 'src');

  /** Every `.ts`/`.tsx` under `src`, which is where a utility can be written. */
  function sourceFiles(directory: string): readonly string[] {
    const found: string[] = [];
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) found.push(...sourceFiles(path));
      else if (/\.tsx?$/.test(entry.name)) found.push(path);
    }
    return found;
  }

  /**
   * The values a colour-taking prefix may carry that are not colour roles.
   *
   * `transparent` is a CSS keyword rather than a token and always will be.
   * The border entries are structural — a side, or a side removed — which is
   * how this system draws a single edge, `edge` having set the width.
   */
  const NOT_A_COLOUR = new Set([
    'transparent',
    'current',
    'inherit',
    'none',
    't',
    'r',
    'b',
    'l',
    'x',
    'y',
    't-0',
    'r-0',
    'b-0',
    'l-0',
    'x-0',
    'y-0',
    't-transparent',
    // A collision rather than an exemption, and worth naming as one. The token
    // is called `border-strong`, so the utility that reaches it is
    // `border-border-strong` — and the text `border-strong`, which is how the
    // token is spelled in its own declaration and in every comment discussing
    // it, is indistinguishable by pattern from a `border-` utility carrying a
    // role named `strong`. The cost of the exemption is that a class list
    // written `border-strong` by mistake is not caught here; it is one token
    // name, it is caught by eye the moment the border disappears, and the
    // alternative is a check that fails on the token table describing itself.
    'strong',
  ]);

  const COLOUR_UTILITY = /(?:^|[\s'"`])(bg|border)-([a-z][a-z0-9-]*)(?![\w-])/g;

  it('names no colour role the token table does not declare', () => {
    const declared = new Set<string>(COLOUR_ROLES);
    const invented: string[] = [];

    for (const file of sourceFiles(SOURCE)) {
      const source = readFileSync(file, 'utf8');
      source.split('\n').forEach((line, index) => {
        for (const [, , name] of line.matchAll(COLOUR_UTILITY)) {
          if (name === undefined) continue;
          if (declared.has(name) || NOT_A_COLOUR.has(name)) continue;
          invented.push(
            `${file.slice(SOURCE.length + 1)}:${String(index + 1)} names ${name}`,
          );
        }
      });
    }

    expect(
      invented,
      'these utilities name a colour role nothing declares, so Tailwind emits no rule for them at all',
    ).toEqual([]);
  });
});
