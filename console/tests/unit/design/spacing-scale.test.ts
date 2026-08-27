import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { compile } from 'tailwindcss';
import { describe, expect, it } from 'vitest';

import { SPACING } from '@/design/tokens';

/**
 * The spacing scale is closed, and this is what compiles the stylesheet to
 * prove it.
 *
 * Both this repository's documentation and the stylesheet's own comment used to
 * claim that "Tailwind is given the seven spacing steps explicitly and no base,
 * so `p-9` is not a utility and produces no CSS at all". It was false for a
 * year. `@theme inline` *adds* `--spacing-1..7`; it never clears the base, so
 * Tailwind's own `--spacing: 0.25rem` survived and `p-9`, `max-h-96`, `h-44`
 * and `w-0.5` all emitted `calc(var(--spacing) * N)`. The scale was documented
 * as enforced twice and was enforced once, by the lint rule — whose list of
 * spacing-taking utilities did not cover heights or widths at all.
 *
 * A claim nothing compiles is a claim that drifts. So the claim is made here,
 * against the real stylesheet, by the same compiler the build uses: an
 * off-scale step must produce no rule, and every declared step must produce
 * one. Reading the CSS is the only way to know — the `@theme` block on its own
 * cannot tell you what it inherited.
 */

// Resolved from the runner's root rather than from `import.meta.url`, for the
// reason `css.test.ts` states: the DOM environment rewrites a module's own URL
// to an http one, and a file cannot be read from that.
const ROOT = process.cwd();
const GLOBALS = readFileSync(join(ROOT, 'src/app/globals.css'), 'utf8');

/**
 * Compile `globals.css` against a candidate list and return the class names it
 * emitted a rule for.
 *
 * One build with every candidate rather than one build each: the compiler is
 * incremental and accumulates candidates across calls, so per-candidate builds
 * would report every earlier candidate as well.
 */
async function emitted(candidates: readonly string[]): Promise<ReadonlySet<string>> {
  const compiler = await compile(GLOBALS, {
    base: join(ROOT, 'src/app'),
    loadStylesheet: (id: string, base: string) => {
      // `globals.css` imports exactly one stylesheet, Tailwind's own entry, and
      // that entry inlines the rest. Anything else reaching here is a new import
      // somebody added, and failing loudly beats compiling a stylesheet that is
      // quietly missing half of itself.
      if (id !== 'tailwindcss') throw new Error(`unexpected @import ${id}`);
      const path = join(ROOT, 'node_modules/tailwindcss/index.css');
      return Promise.resolve({ path, base, content: readFileSync(path, 'utf8') });
    },
  });

  const css = compiler.build([...candidates]);
  const found = new Set<string>();
  for (const match of css.matchAll(/\.((?:\\.|[-\w])+)\s*\{/g)) {
    found.add((match[1] ?? '').replace(/\\(.)/g, '$1'));
  }
  return found;
}

/** The seven steps, spread across the utilities that take one. */
const ON_SCALE = Object.keys(SPACING).flatMap((step) => [
  `p-${step}`,
  `mt-${step}`,
  `gap-${step}`,
  `h-${step}`,
  `w-${step}`,
  `max-w-${step}`,
]);

/**
 * Zero, which is the removal of a step rather than an eighth step.
 *
 * `--spacing-0` is declared alongside the closure for exactly these: `inset-0`
 * pins to an edge and `min-w-0` lets a flex child shrink, and a scale that
 * could not say "none" would be worked around with an arbitrary value.
 */
const ZERO = ['p-0', 'mt-0', 'inset-0', 'top-0', 'min-w-0', 'min-h-0', 'h-0'];

/** Steps the scale does not declare, one per utility family that takes one. */
const OFF_SCALE = [
  'p-9',
  'p-13',
  'mt-11',
  'gap-9',
  'space-y-9',
  'max-h-96',
  'max-h-64',
  'h-44',
  'w-0.5',
  'min-h-44',
  'size-12',
  'translate-x-9',
  // Not a spacing step at all: Tailwind's container scale, a second set of
  // lengths nobody here declared. It is closed with the spacing base, because
  // a width off the design's own scale is off the scale whichever namespace
  // it came in through.
  'max-w-md',
  'max-w-2xl',
];

describe('the spacing scale, as the stylesheet actually compiles', () => {
  it('emits a rule for every declared step', async () => {
    const rules = await emitted(ON_SCALE);
    const missing = ON_SCALE.filter((candidate) => !rules.has(candidate));

    expect(
      missing,
      'a declared step compiles to nothing, so a component cannot use it',
    ).toEqual([]);
  });

  it('emits a rule for zero, which removes a step rather than being one', async () => {
    const rules = await emitted(ZERO);
    const missing = ZERO.filter((candidate) => !rules.has(candidate));

    expect(missing, 'closing the scale took the zero utilities with it').toEqual([]);
  });

  it('emits nothing at all for a step the scale does not declare', async () => {
    const rules = await emitted(OFF_SCALE);
    const survivors = OFF_SCALE.filter((candidate) => rules.has(candidate));

    expect(
      survivors,
      'these compile to a length nobody declared, so the scale is not closed',
    ).toEqual([]);
  });
});
