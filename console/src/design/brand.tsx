import type { ReactNode } from 'react';

import { cx } from './cx';

/**
 * The mark, and the name beside it.
 *
 * Drawn here rather than loaded from `public/brand/`, for the reason the icon
 * set gives about itself: a mark in an `<img>` cannot inherit `currentColor`,
 * so it would arrive as a fixed colour and be wrong in one of the two themes.
 * Inline, it is whatever colour the thing around it is — which is the whole of
 * the mark's colour rule.
 *
 * The public files still exist, because everything outside this application
 * needs them, and a test holds the geometry here equal to the geometry there.
 */

/**
 * The mark's geometry, at the cut drawn for 24px and below.
 *
 * The small cut rather than the main one: this is the size a navigation entry
 * and a favicon are, and reducing the main cut to menu size tapers its eight
 * points until they close on one another and the hole disappears. Using the
 * wrong cut is the most likely mistake this design can suffer.
 */
export const MARK_SMALL_PATH =
  'M32 3 L37.93 17.68 L52.51 11.49 L46.32 26.07 L61 32 L46.32 37.93 ' +
  'L52.51 52.51 L37.93 46.32 L32 61 L26.07 46.32 L11.49 52.51 L17.68 37.93 ' +
  'L3 32 L17.68 26.07 L11.49 11.49 L26.07 17.68 Z ' +
  'M32 25.5 A6.5 6.5 0 1 0 32 38.5 A6.5 6.5 0 1 0 32 25.5 Z';

/**
 * The two runs of the name, and which one carries the accent.
 *
 * The colour does not decorate. It says where the proper noun ends and what the
 * thing is begins, which is why the split is declared rather than sliced out of
 * the name at a hard-coded offset — and why a test holds the two halves equal
 * to the whole in every language the console speaks.
 */
export const WORDMARK = { name: 'Ninja', discipline: 'SRE' } as const;

export interface MarkProps {
  readonly className?: string;
}

/**
 * The mark on its own, inheriting whatever colour it is placed in.
 *
 * Decorative by default. Wherever it appears the name is beside it, so an
 * accessible name here would be the product announced twice.
 */
export function Mark({ className }: MarkProps): ReactNode {
  return (
    <svg
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
      fill="currentColor"
      className={cx('size-5 shrink-0', className)}
    >
      <path fillRule="evenodd" d={MARK_SMALL_PATH} />
    </svg>
  );
}

export interface LockupProps {
  /** The whole name, for anything that reads rather than looks. */
  readonly name: string;
  readonly className?: string;
}

/**
 * The mark and the name, horizontal.
 *
 * The name is one accessible string and two visible runs: a reader hears
 * "NinjaSRE", and a viewer sees where the proper noun ends.
 */
export function Lockup({ name, className }: LockupProps): ReactNode {
  return (
    <span className={cx('flex items-center gap-2', className)}>
      <Mark className="text-accent" />
      <span className="text-strong">
        <span className="sr-only">{name}</span>
        <span aria-hidden="true">
          {WORDMARK.name}
          <span className="text-accent">{WORDMARK.discipline}</span>
        </span>
      </span>
    </span>
  );
}
