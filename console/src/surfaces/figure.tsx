import type { ReactNode } from 'react';

import { StatTile } from '@/components/surface';
import { ArrowRightIcon } from '@/design/icons';

/**
 * A summary figure, with the two things that make one worth showing.
 *
 * A period and a comparison, so the number means something; and a drill-down, so
 * a reader who does not believe it can go and look. **A figure with neither is
 * not rendered**, and that is enforced here rather than reviewed: the type has no
 * way to spell a figure without a destination, and a destination that is present
 * and empty throws.
 *
 * The rule removes most decorative metrics at the point somebody writes one,
 * which is the only point at which removing them is cheap. A dashboard becomes a
 * wall of numbers one well-meant tile at a time.
 */

export interface FigureProps {
  readonly label: string;
  readonly value: string;
  /** The period, and the comparison against the previous one. Never decoration. */
  readonly context: string;
  /** The list this figure counts. Required, and required to be somewhere. */
  readonly href: string;
  /** What the link is called, for a reader who hears only the link. */
  readonly drillLabel: string;
  readonly icon?: ReactNode;
  readonly trend?: 'up' | 'down' | 'flat';
}

/** One figure, its comparison, and the list it counts. */
export function Figure({
  label,
  value,
  context,
  href,
  drillLabel,
  icon,
  trend = 'flat',
}: FigureProps): ReactNode {
  if (href.trim() === '') {
    throw new Error(
      `The figure "${label}" has no drill-down. A number a reader cannot go and check is a number this console does not show.`,
    );
  }
  return (
    <a
      href={href}
      data-testid="figure"
      data-figure={label}
      className="relative block rounded-3 motion-hover hover:opacity-90"
    >
      <StatTile
        label={label}
        value={value}
        context={context}
        trend={trend}
        {...(icon === undefined ? {} : { icon })}
      />
      {/* A visible affordance rather than one only a screen reader hears: a
          card that only announces its own link to assistive technology is a
          card a sighted reader has to already know is clickable. */}
      <span
        data-testid="figure-drill"
        aria-hidden="true"
        className="absolute right-3 top-3 text-muted"
      >
        <ArrowRightIcon />
      </span>
      <span className="sr-only">{drillLabel}</span>
    </a>
  );
}
