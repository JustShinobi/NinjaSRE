import type { ReactNode } from 'react';
import { useId } from 'react';

import { cx } from '@/design/cx';

/**
 * The two containers everything else sits in.
 *
 * Both of them declare an empty state, a loading state and an error state,
 * because a container that can show nothing has to say what nothing means. The
 * first live run of the previous console showed eight empty tables, and a fresh
 * deployment that looks broken is indistinguishable from one that is.
 *
 * Neither container changes its box between those states. A card that is
 * shorter while it loads is a card that pushes the rest of the page down when
 * the data arrives, which is the movement the fifth design principle forbids.
 */

export const SURFACE_STATES = ['ready', 'loading', 'empty', 'error'] as const;

export type SurfaceState = (typeof SURFACE_STATES)[number];

export interface CardProps {
  readonly title: string;
  readonly state?: SurfaceState;
  readonly action?: ReactNode;
  readonly emptyMessage?: string;
  readonly errorMessage?: string;
  readonly children?: ReactNode;
}

/**
 * A titled panel.
 *
 * The title is not decoration: it names the region, so a panel that fails can
 * say which panel failed and a screen reader can list what is on the page.
 */
export function Card({
  title,
  state = 'ready',
  action,
  emptyMessage,
  errorMessage,
  children,
}: CardProps): ReactNode {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      data-state={state}
      className="bg-raised edge border-border rounded-3 shadow-1 flex flex-col"
    >
      <header className="flex items-center gap-2 px-4 py-3 edge border-border border-t-0 border-x-0">
        <h3 id={headingId} className="text-strong">
          {title}
        </h3>
        {action === undefined ? null : <div className="ml-auto">{action}</div>}
      </header>
      <div className="p-4">
        {state === 'loading' ? (
          <p role="status" className="text-muted text-small">
            Loading {title}…
          </p>
        ) : null}
        {state === 'empty' ? (
          <p className="text-muted text-small">{emptyMessage ?? 'Nothing to show.'}</p>
        ) : null}
        {state === 'error' ? (
          <p role="alert" className="text-danger text-small">
            {errorMessage ?? 'This panel could not be loaded.'}
          </p>
        ) : null}
        {state === 'ready' ? children : null}
      </div>
    </section>
  );
}

export interface StatTileProps {
  readonly label: string;
  readonly value: string;
  /**
   * A comparison to the previous period, or a breakdown.
   *
   * Mandatory. A figure with no context is a figure nobody can act on, and this
   * console does not render one — the component throws rather than shipping a
   * number that means nothing.
   */
  readonly context: string;
  readonly icon?: ReactNode;
  readonly state?: SurfaceState;
  readonly trend?: 'up' | 'down' | 'flat';
}

const TREND_SKIN: Readonly<Record<'up' | 'down' | 'flat', string>> = {
  up: 'text-success',
  down: 'text-danger',
  flat: 'text-muted',
};

/** One figure, its label, and the line that makes it actionable. */
export function StatTile({
  label,
  value,
  context,
  icon,
  state = 'ready',
  trend = 'flat',
}: StatTileProps): ReactNode {
  if (context.trim() === '') {
    throw new Error(
      `The stat tile "${label}" has no context line. A figure with no comparison and no breakdown is a figure nobody can act on, so this console does not render one.`,
    );
  }
  return (
    <div
      data-state={state}
      className="bg-raised edge border-border rounded-3 shadow-1 p-4 flex flex-col gap-1"
    >
      <span className="text-meta text-muted flex items-center gap-1">
        {icon}
        {label}
      </span>
      <span
        data-testid="stat-value"
        className={cx(
          // `rounded-2` is on both states rather than only on the placeholder:
          // a radius that appears while loading is a geometry change, which is
          // the shift this component exists to avoid.
          'text-display tabular-nums rounded-2',
          state === 'loading' ? 'bg-neutral-bg text-transparent' : '',
        )}
      >
        {value}
      </span>
      <span className={cx('text-meta', TREND_SKIN[trend])}>{context}</span>
    </div>
  );
}
