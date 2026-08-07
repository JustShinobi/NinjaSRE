'use client';

import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { contrastRatio } from '@/design/contrast';
import { ICON_SIZES } from '@/design/css';
import { RESOURCE_STATUSES } from '@/design/status';
import {
  BORDER_WIDTHS,
  bodyPairs,
  boundaryPairs,
  DURATIONS,
  RADII,
  SPACING,
  type Theme,
  TYPE_STEPS,
} from '@/design/tokens';

/**
 * The token sections of the gallery.
 *
 * These are not documentation about the design system; they are the design
 * system rendered. Every ratio below is computed at render time from the same
 * table the contrast test measures, so a swatch cannot show a number that is no
 * longer true — which is the failure mode a hand-written colour chart has from
 * the day after it is written.
 */

/** Which theme's numbers to print. The swatches themselves follow the document. */
export interface TokenSectionProps {
  readonly theme: Theme;
}

/** Every measured pair, with the ratio the arithmetic gives it right now. */
export function ColourSection({ theme }: TokenSectionProps): ReactNode {
  const measured = [
    ...bodyPairs(theme).map((pair) => ({ ...pair, threshold: '4.5' })),
    ...boundaryPairs(theme).map((pair) => ({ ...pair, threshold: '3' })),
  ];
  return (
    <div className="flex flex-col gap-4">
      <p className="text-small text-muted max-w-prose">
        Colour is declared by role, never by hue. Every pair is measured against WCAG
        2.1 from the token table itself: body text needs 4.5:1, a control boundary needs
        3:1. Both themes declare the same names, so a screen written against tokens
        works in both by construction.
      </p>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {measured.map((pair) => (
          <li
            key={`${pair.what}-${pair.threshold}`}
            className="rounded-2 edge border-border overflow-hidden"
          >
            <span
              className="flex items-center justify-center h-6 text-small"
              style={{ background: pair.background, color: pair.foreground }}
            >
              Aa
            </span>
            <span className="block px-2 py-1 bg-raised">
              <span className="block text-meta">{pair.what}</span>
              <span className="block text-meta text-muted font-mono tabular-nums">
                {contrastRatio(pair.foreground, pair.background).toFixed(2)}:1 · needs{' '}
                {pair.threshold}
              </span>
            </span>
          </li>
        ))}
      </ul>
      <p className="text-small text-muted max-w-prose">
        Status never rides on colour alone. Each state carries a label and a shape, so
        it survives a viewer who cannot separate the hues.
      </p>
      <ul className="flex flex-wrap gap-3">
        {[...RESOURCE_STATUSES, 'quiesced'].map((status) => (
          <li key={status}>
            <Badge status={status} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The type, spacing, radius, border and duration scales, as closed sets. */
export function ScaleSection(): ReactNode {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="flex flex-col gap-2">
        <h3 className="text-strong">Type</h3>
        <ul className="flex flex-col gap-2">
          {Object.entries(TYPE_STEPS).map(([name, step]) => (
            <li key={name} className="flex items-baseline gap-3">
              <code className="text-meta text-muted font-mono shrink-0 whitespace-nowrap">
                {name} {step.size}/{step.line}
              </code>
              <span
                style={{ fontSize: `${String(step.size)}px`, fontWeight: step.weight }}
              >
                Quorum margin is zero
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <h3 className="text-strong">Spacing</h3>
          <ul className="flex flex-col gap-1">
            {Object.entries(SPACING).map(([step, value]) => (
              <li key={step} className="flex items-center gap-3 text-meta text-muted">
                <code className="font-mono shrink-0 whitespace-nowrap">
                  s{step} {value}
                </code>
                <span
                  className="block h-3 bg-accent-bg"
                  style={{ inlineSize: `${String(value)}px` }}
                />
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-2">
          <h3 className="text-strong">Radius, border, duration, icon</h3>
          <ul className="flex flex-col gap-1 text-meta text-muted font-mono">
            <li>radius · {Object.values(RADII).join(' · ')}</li>
            <li>border · {Object.values(BORDER_WIDTHS).join(' · ')}</li>
            <li>duration · {Object.values(DURATIONS).join(' · ')}</li>
            <li>icon · {Object.values(ICON_SIZES).join(' · ')}</li>
          </ul>
          <p className="text-meta text-muted max-w-prose">
            Closed sets. A lint rule rejects any value that is not on one, which is the
            only mechanism that keeps a design system from decaying into suggestions.
            Under reduced motion every duration becomes the first member of the scale —
            removed, not shortened.
          </p>
        </div>
      </div>
    </div>
  );
}
