import { describe, expect, it } from 'vitest';

import { findings } from '../../../eslint-rules/no-design-literals.mjs';

/**
 * The lint half of the scale, and the utilities it used to have nothing to say
 * about.
 *
 * The stylesheet closes the scale, so an off-scale step now compiles to
 * nothing; `spacing-scale.test.ts` proves that. This is the other half, and it
 * matters for a reason the closure does not cover: a utility that produces no
 * CSS is silent. The element keeps whatever it inherited and the screen looks
 * *nearly* right, which is the failure mode that survives review. Lint is what
 * turns that silence into a named error at the call site.
 *
 * Its list of spacing-taking utilities covered padding, margin, gap and inset
 * and stopped there — so `max-h-96`, `h-44` and `w-0.5` passed lint for as long
 * as they existed, while the stylesheet, which everyone believed was the
 * stricter of the two checks, was quietly compiling them.
 */

/** The message ids a finding can carry, so a test asserts the kind as well. */
function kinds(text: string): readonly string[] {
  return findings(text).map(([messageId]) => messageId);
}

describe('utilities whose numeric step must be on the spacing scale', () => {
  it.each([
    'p-9',
    'mt-11',
    'gap-9',
    'inset-9',
    'size-12',
    'h-44',
    'w-0.5',
    'max-h-96',
    'max-h-64',
    'max-w-96',
    'min-h-44',
    'min-w-96',
    'translate-x-9',
    'translate-y-9',
    '-translate-x-9',
  ])('rejects %s', (candidate) => {
    expect(kinds(candidate), `${candidate} passed the scale check`).toContain(
      'offScale',
    );
  });

  it.each([
    'p-4',
    'gap-3',
    'h-6',
    'w-7',
    'max-h-5',
    'min-w-2',
    'size-control',
    'translate-x-1',
    // Zero is the removal of a step rather than an eighth one, and the
    // stylesheet declares `--spacing-0` so that it keeps working.
    'p-0',
    'inset-0',
    'min-w-0',
    'max-h-0',
    // Named measurements: not steps, and not pretending to be.
    'max-h-scroll-pane',
    'h-scroll-slot',
    'max-w-reading',
    'w-stroke-emphasis',
    'w-column-instant',
    'h-control',
    'w-full',
    'h-screen',
  ])('accepts %s', (candidate) => {
    expect(kinds(candidate), `${candidate} was reported off-scale`).not.toContain(
      'offScale',
    );
  });
});
