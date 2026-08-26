import type { ReactNode } from 'react';
import { useId } from 'react';

import { cx } from '@/design/cx';
import type { SemanticRole } from '@/design/tokens';

/**
 * Page structure, as components rather than as per-page CSS.
 *
 * This is the smallest part of the feature and one of the load-bearing ones. A
 * gutter written into a page's own stylesheet is a gutter that disagrees with
 * the next page, and by the fourth screen nobody can say what the gutter is
 * supposed to be. Four components remove the question.
 */

export interface PageHeaderProps {
  readonly title: string;
  /**
   * The full title, when `title` is a clipped version of something longer.
   * Absent for an ordinary title — a tooltip repeating exactly what is
   * already on the screen teaches a reader to stop trusting tooltips.
   */
  readonly titleTooltip?: string | undefined;
  readonly context: string;
  readonly icon?: ReactNode;
  readonly actions?: ReactNode;
  /**
   * What state the page is in, as counts rather than as a sentence.
   *
   * Separate from `actions` because they are different things wearing the same
   * corner: an action is something to press, a count is something to read, and
   * a screen that put its statistics through the actions slot got them styled
   * as a control and sized like a caption.
   */
  readonly meta?: ReactNode;
}

/**
 * The top of a page: what this is, what state it is in, what can be done to it.
 *
 * The actions come after the title in the reading order however they are
 * placed, because a keyboard user should reach the page's name before its
 * controls.
 */
export function PageHeader({
  title,
  titleTooltip,
  context,
  icon,
  actions,
  meta,
}: PageHeaderProps): ReactNode {
  // Stacks below the small breakpoint. Side by side, the actions take whatever
  // they need and the title gets the remainder, which at 320px was narrower
  // than the word "Resources" — so the page's own name broke across two lines
  // beside a block of statistics. Above the breakpoint nothing moves: the
  // actions go back to the right, where they were.
  return (
    <header className="flex flex-col sm:flex-row items-start gap-3 mb-5">
      {icon === undefined ? null : (
        <span className="flex items-center justify-center size-6 rounded-3 bg-accent-bg text-accent shrink-0">
          {icon}
        </span>
      )}
      <div className="min-w-0">
        {/*
          Wraps rather than clips. `truncate` here put an ellipsis through the
          page's own name at 320px — "Resourc…" — and the only way back to the
          full string was the tooltip, which `titleTooltip` deliberately leaves
          unset for an ordinary title and which a touch device has no way to
          open at all. A clipped label in a table cell is a trade; a clipped
          page name is a screen that will not say where it is. Two lines of
          heading cost less than that.
        */}
        <h1 className="text-title break-words" title={titleTooltip}>
          {title}
        </h1>
        <p className="text-meta text-muted">{context}</p>
      </div>
      {meta === undefined && actions === undefined ? null : (
        <div className="sm:ml-auto flex items-center gap-5">
          {meta}
          {actions === undefined ? null : <div className="flex gap-2">{actions}</div>}
        </div>
      )}
    </header>
  );
}

/** One part of a count strip: how many of what, in which role's colour. */
export interface CountPart {
  readonly label: string;
  readonly value: number;
  /**
   * Which semantic role colours the number. Absent leaves it in body colour,
   * which is right for a part that is neither good nor bad.
   */
  readonly role?: SemanticRole;
}

export interface CountStripProps {
  /** The whole, which the parts are checked against. */
  readonly total: { readonly label: string; readonly value: number };
  /** The parts the total is made of. These are expected to add up to it. */
  readonly parts: readonly CountPart[];
  /**
   * Counts that sit beside the total rather than inside it.
   *
   * The estate's absent resources are the case this exists for: they carry a
   * health like any other and are deliberately excluded from `total`, because
   * "watched" means what the estate currently has. Folded in with the parts
   * they made the arithmetic overshoot by exactly their own number, which
   * reads as the page being wrong about itself.
   */
  readonly aside?: readonly CountPart[];
  /** Said when the parts fall short of the total, naming what is unaccounted for. */
  readonly shortfallLabel?: string;
}

/** Which token colours each role's number. */
const COUNT_ROLE: Readonly<Record<SemanticRole, string>> = {
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
  info: 'text-info',
  neutral: 'text-muted',
};

/**
 * A page header's counts, with the arithmetic proved rather than trusted.
 *
 * Resources shipped "97 watched · 76 healthy · 0 degraded · 13 unhealthy" — a
 * sentence with four holes, three of which added to 89. The eight resources in
 * a state the sentence had no hole for were visible in the table below it, so
 * the page contradicted itself within one screenful.
 *
 * A sentence cannot be made safe by filling in the missing hole, because the
 * next state added to the enumeration reopens the same gap. This takes the
 * parts and the whole separately and *checks* them, marks itself when they
 * disagree, and shows the remainder rather than hiding it. `data-balanced` is on
 * the element so the suite can hold a real screen's real numbers to it.
 */
export function CountStrip({
  total,
  parts,
  aside = [],
  shortfallLabel,
}: CountStripProps): ReactNode {
  const counted = parts.reduce((sum, part) => sum + part.value, 0);
  const shortfall = total.value - counted;
  const balanced = shortfall === 0;
  // A remainder is something the parts have not reached. Parts that overshoot
  // the total are a different fault — the breakdown and the total disagree
  // about what they are counting — and rendering that as "-5 unaccounted for"
  // is worse than the sentence it was meant to replace. It is still marked
  // unbalanced, and the total says so on hover, but nothing invents a cell for
  // a negative remainder.
  const remainder = shortfall > 0 ? shortfall : 0;
  return (
    <div
      data-testid="count-strip"
      data-balanced={String(balanced)}
      className="flex items-baseline gap-5"
    >
      <div className="flex flex-col items-end">
        <span
          data-testid="count-total"
          className={cx('text-section', balanced ? '' : 'text-warning')}
          {...(balanced
            ? {}
            : {
                title: `${String(counted)} / ${String(total.value)}`,
              })}
        >
          {total.value}
        </span>
        <span className="text-meta text-muted">{total.label}</span>
      </div>
      {parts.map((part) => (
        <div
          key={part.label}
          data-testid="count-part"
          className="flex flex-col items-end"
        >
          <span
            className={cx(
              'text-section',
              part.role === undefined ? '' : COUNT_ROLE[part.role],
            )}
          >
            {part.value}
          </span>
          <span className="text-meta text-muted">{part.label}</span>
        </div>
      ))}
      {aside.length === 0 ? null : (
        // Set off by a rule, because the eye reads a row of numbers as one sum
        // and these are not in it.
        <div className="flex items-baseline gap-5 border-l border-border pl-5">
          {aside.map((part) => (
            <div
              key={part.label}
              data-testid="count-aside"
              className="flex flex-col items-end"
            >
              <span className="text-section text-muted">{part.value}</span>
              <span className="text-meta text-muted">{part.label}</span>
            </div>
          ))}
        </div>
      )}
      {remainder === 0 || shortfallLabel === undefined ? null : (
        <div data-testid="count-shortfall" className="flex flex-col items-end">
          <span className="text-section text-muted">{remainder}</span>
          <span className="text-meta text-muted">{shortfallLabel}</span>
        </div>
      )}
    </div>
  );
}

export interface SectionProps {
  readonly title: string;
  readonly description?: string;
  readonly children: ReactNode;
}

/** A named division of a page, which is a landmark rather than a heading and a gap. */
export function Section({ title, description, children }: SectionProps): ReactNode {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="mb-6 flex flex-col gap-4">
      <div>
        <h2 id={headingId} className="text-section">
          {title}
        </h2>
        {description === undefined ? null : (
          <p className="text-meta text-muted">{description}</p>
        )}
      </div>
      {children}
    </section>
  );
}

export interface SplitLayoutProps {
  readonly primary: ReactNode;
  readonly secondary: ReactNode;
}

/**
 * A primary surface with a context rail.
 *
 * Two thirds and one third above the breakpoint; one column below it, with the
 * rail underneath. The rail wraps rather than shrinking because a context rail
 * at three hundred pixels is a column of wrapped words nobody reads.
 */
export function SplitLayout({ primary, secondary }: SplitLayoutProps): ReactNode {
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
      <div className="lg:col-span-2 min-w-0">{primary}</div>
      <div className="min-w-0">{secondary}</div>
    </div>
  );
}

export interface ContentWidthProps {
  readonly children: ReactNode;
}

/** The measure cap, so a sentence does not run the width of a wide monitor. */
export function ContentWidth({ children }: ContentWidthProps): ReactNode {
  return <div className="mx-auto w-full max-w-page px-5">{children}</div>;
}
