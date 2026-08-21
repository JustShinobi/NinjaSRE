import type { ReactNode } from 'react';

import { cx } from '@/design/cx';
import { type Shape, statusPresentation } from '@/design/status';
import type { SemanticRole } from '@/design/tokens';

/**
 * Status, drawn twice.
 *
 * Every state in this console carries a label *and* a shape. Roughly one man in
 * twelve cannot separate this palette's success from its danger, and a console
 * whose only difference between "healthy" and "unhealthy" is a hue is a console
 * those operators are reading at three in the morning without the information.
 *
 * The shape is not decoration on top of the colour. It is the second carrier,
 * and the two states that share the neutral role — unknown and stale — carry
 * different ones for that reason, which is asserted rather than assumed.
 */

/** The tint, foreground and boundary each role wears. */
const ROLE_SKIN: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-success-bg text-success border-success',
  warning: 'bg-warning-bg text-warning border-warning',
  danger: 'bg-danger-bg text-danger border-danger',
  info: 'bg-info-bg text-info border-info',
  neutral: 'bg-neutral-bg text-neutral border-border-strong',
};

/** The fill each role gives a shape. */
const ROLE_FILL: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-success border-success',
  warning: 'bg-warning border-warning',
  danger: 'bg-danger border-danger',
  info: 'bg-info border-info',
  neutral: 'bg-neutral border-neutral',
};

/**
 * How each shape is drawn.
 *
 * Sizes come from the icon scale rather than from the spacing scale: these are
 * glyphs sitting on a text baseline, and a glyph that grew with the padding
 * would drift away from the letters beside it.
 */
const SHAPE_CLASS: Readonly<Record<Shape, string>> = {
  'filled-circle': 'icon-inline rounded-full',
  'hollow-circle': 'icon-inline rounded-full bg-transparent edge-ring',
  'dimmed-circle': 'icon-inline rounded-full opacity-50',
  square: 'icon-inline',
  'rotated-square': 'icon-inline rotate-45',
  triangle: 'icon-inline clip-triangle',
  dash: 'icon-inline h-0 edge-ring rounded-full',
};

export interface ShapeMarkProps {
  readonly shape: Shape;
  readonly role: SemanticRole;
  readonly className?: string;
}

/** The glyph itself, which is what carries the meaning when colour cannot. */
function ShapeMark({ shape, role, className }: ShapeMarkProps): ReactNode {
  return (
    <span
      data-shape={shape}
      aria-hidden="true"
      className={cx(
        SHAPE_CLASS[shape],
        ROLE_FILL[role],
        'edge inline-block shrink-0',
        className,
      )}
    />
  );
}

export interface BadgeProps {
  /** The status as the API reported it. Never translated, never trimmed away. */
  readonly status: string;
  readonly className?: string;
}

/**
 * A status, as a chip: shape, then the word.
 *
 * The word is always the status the API sent. A status the console has never
 * heard of gets the neutral role and its own text — never blank, never an
 * error, because a provider one version ahead is not a fault.
 */
export function Badge({ status, className }: BadgeProps): ReactNode {
  const presented = statusPresentation(status);
  return (
    <span
      data-role={presented.role}
      data-known={presented.known}
      className={cx(
        'inline-flex items-center gap-1 px-2 rounded-1 edge text-micro uppercase',
        ROLE_SKIN[presented.role],
        className,
      )}
    >
      <ShapeMark shape={presented.shape} role={presented.role} />
      {presented.label}
    </span>
  );
}

export interface StatusDotProps {
  readonly status: string;
  /**
   * Whether this dot is the only thing saying what the status is.
   *
   * Normally it is not — a label sits beside it, and a dot that announced
   * itself would say "healthy" twice on every row. When a dense table really
   * does show nothing else, this gives the shape an accessible name.
   */
  readonly standalone?: boolean;
  readonly className?: string;
}

/** The smallest status there is: one shape, in one role's colour. */
export function StatusDot({
  status,
  standalone = false,
  className,
}: StatusDotProps): ReactNode {
  const presented = statusPresentation(status);
  if (!standalone) {
    return (
      <ShapeMark
        shape={presented.shape}
        role={presented.role}
        className={cx('', className)}
      />
    );
  }
  return (
    <span
      role="img"
      aria-label={presented.label}
      data-shape={presented.shape}
      data-role={presented.role}
      className={cx(
        SHAPE_CLASS[presented.shape],
        ROLE_FILL[presented.role],
        'edge inline-block shrink-0',
        className,
      )}
    />
  );
}
