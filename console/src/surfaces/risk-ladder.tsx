import type { ReactNode } from 'react';

import { cx } from '@/design/cx';
import type { SemanticRole } from '@/design/tokens';

/**
 * One class of action, drawn as the rung of a ladder that it is.
 *
 * "What would happen, by class of action" listed trivial, low, moderate, high
 * and critical at one size, one weight and one chip colour, in lowercase
 * monospace, each followed by two paragraphs. The one thing the screen exists
 * to communicate — that these escalate, and that the deployment's posture sits
 * somewhere along them — was the one thing it did not draw, and a reader got to
 * it only by reading five near-identical entries and noticing the order.
 *
 * **The rungs carry it, never the hue.** Roughly one man in twelve cannot
 * separate the greens and reds this palette uses, which is the same reason
 * every status here carries a shape; a ladder told in colour is a ladder those
 * readers do not have. The count is stated outright as well, for anything that
 * cannot see the drawing at all.
 *
 * A class the scale has never met draws no rungs. Placing it at the bottom
 * would be a guess rendered as a measurement — and the class it would be
 * guessing about is the one an operator most needs not to be lied to about.
 */

/** The scale, least to most dangerous, as `platform/autonomy/risk.py` declares it. */
export const RISK_CLASSES = ['trivial', 'low', 'moderate', 'high', 'critical'] as const;

export type RiskClass = (typeof RISK_CLASSES)[number];

/** Which role colours each rung. Two safe, one cautionary, two dangerous. */
const RISK_ROLE: Readonly<Record<RiskClass, SemanticRole>> = {
  trivial: 'success',
  low: 'success',
  moderate: 'warning',
  high: 'danger',
  critical: 'danger',
};

/** The fill each role gives a filled rung. */
const RUNG_FILL: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
  neutral: 'bg-neutral',
};

export interface RiskLadderProps {
  /** The class as the policy reports it. */
  readonly riskClass: string;
  /** The same class, in words. Resolved by the caller, never spelled here. */
  readonly label: string;
  readonly className?: string;
}

export function RiskLadder({
  riskClass,
  label,
  className,
}: RiskLadderProps): ReactNode {
  // Found rather than indexed, so the class carries its own type the whole way
  // down and neither a cast nor an assertion is needed to read its role.
  const placed = RISK_CLASSES.find((step) => step === riskClass);
  const rank = placed === undefined ? -1 : RISK_CLASSES.indexOf(placed);
  const role: SemanticRole = placed === undefined ? 'neutral' : RISK_ROLE[placed];
  return (
    <span className={cx('flex items-center gap-3', className)}>
      {placed === undefined ? null : (
        <span
          data-testid="risk-ladder"
          role="img"
          aria-label={`${String(rank + 1)} of ${String(RISK_CLASSES.length)}`}
          // Left to right, not stacked. Five short bars in a column read as a
          // menu glyph — which is what they looked like on the running screen —
          // and a scale that has to be explained is not carrying its meaning.
          // A row fills the way a meter fills, which is the reading wanted.
          className="flex gap-1 shrink-0"
        >
          {RISK_CLASSES.map((step, index) => (
            <span
              key={step}
              data-testid="risk-rung"
              data-filled={index <= rank ? 'true' : 'false'}
              className={cx(
                'block w-2 h-1 rounded-1',
                // An unfilled rung is `border-strong`, not `border`. At four
                // pixels by one the fainter of the two is not visible at all,
                // and an invisible empty rung turns one-of-five into a lone
                // dash floating in space.
                index <= rank ? RUNG_FILL[role] : 'bg-border-strong',
              )}
            />
          ))}
        </span>
      )}
      <span data-testid="risk-class" className="text-strong">
        {label}
      </span>
    </span>
  );
}
