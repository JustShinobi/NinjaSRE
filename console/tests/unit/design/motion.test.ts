import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { DURATIONS } from '@/design/tokens';

/**
 * The three motion primitives the board names, as text in the published
 * stylesheet — the same technique `css.test.ts` already uses for the token
 * block, because neither a keyframe nor a media query is a value `vitest`'s
 * jsdom actually computes; the source is the only thing here that can be
 * held to a claim.
 *
 * `pulse-live` predates this feature (`AutoRefresh`'s live mark already used
 * it); `slide-in` and `stage-shimmer` are new. All three are asserted the
 * same way, because after this feature there is no difference between them —
 * a vocabulary entry is a vocabulary entry regardless of which task added it.
 */

const GLOBALS = readFileSync(join(process.cwd(), 'src/app/globals.css'), 'utf8');

/** Every `@media (prefers-reduced-motion: reduce) { … }` block, concatenated. */
function reducedMotionBlocks(css: string): string {
  const blocks: string[] = [];
  const marker = '@media (prefers-reduced-motion: reduce)';
  let from = 0;
  for (;;) {
    const opened = css.indexOf(marker, from);
    if (opened === -1) break;
    const start = css.indexOf('{', opened);
    let depth = 0;
    let end = start;
    for (let index = start; index < css.length; index += 1) {
      if (css[index] === '{') depth += 1;
      if (css[index] === '}') {
        depth -= 1;
        if (depth === 0) {
          end = index;
          break;
        }
      }
    }
    blocks.push(css.slice(start + 1, end));
    from = end + 1;
  }
  return blocks.join('\n');
}

describe('the three motion primitives', () => {
  it.each(['pulse-live', 'slide-in', 'stage-shimmer'] as const)(
    'declares a %s utility',
    (name) => {
      expect(GLOBALS, `no "@utility ${name}" declared`).toMatch(
        new RegExp(`@utility ${name}\\b`),
      );
    },
  );

  it("reads pulse-live's duration from --dur-pulse", () => {
    // The ring is the animated element; the utility itself is the positioning
    // context (see the comment beside `pulse-live` in globals.css).
    const ringRule = /@utility pulse-live-ring\s*\{[^}]*\}/.exec(GLOBALS)?.[0] ?? '';
    expect(ringRule, 'no @utility pulse-live-ring block found').not.toBe('');
    expect(ringRule).toContain('var(--dur-pulse)');
  });

  it("reads slide-in's duration from --dur-slide", () => {
    const rule = /@utility slide-in\s*\{[^}]*\}/.exec(GLOBALS)?.[0] ?? '';
    expect(rule, 'no @utility slide-in block found').not.toBe('');
    expect(rule).toContain('var(--dur-slide)');
  });

  it("reads stage-shimmer's duration from --dur-shimmer", () => {
    const rule = /@utility stage-shimmer\s*\{[^}]*\}/.exec(GLOBALS)?.[0] ?? '';
    expect(rule, 'no @utility stage-shimmer block found').not.toBe('');
    expect(rule).toContain('var(--dur-shimmer)');
  });

  it('DURATIONS carries the three named tempos, on the closed scale', () => {
    expect(DURATIONS.pulse).toBe(2000);
    expect(DURATIONS.slide).toBe(240);
    expect(DURATIONS.shimmer).toBe(1600);
  });

  it('a single prefers-reduced-motion block resolves all three primitives to animation: none', () => {
    const reduced = reducedMotionBlocks(GLOBALS);
    expect(reduced, 'no @media (prefers-reduced-motion: reduce) block at all').not.toBe(
      '',
    );
    for (const name of ['pulse-live-ring', 'slide-in', 'stage-shimmer']) {
      const rule = new RegExp(`\\.${name}[^{]*\\{[^}]*animation:\\s*none[^}]*\\}`);
      expect(
        rule.test(reduced),
        `no rule under prefers-reduced-motion sets ".${name}" to "animation: none"`,
      ).toBe(true);
    }
  });
});
