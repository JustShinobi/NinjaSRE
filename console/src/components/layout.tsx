import type { ReactNode } from 'react';
import { useId } from 'react';

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
}: PageHeaderProps): ReactNode {
  return (
    <header className="flex items-start gap-3 mb-5">
      {icon === undefined ? null : (
        <span className="flex items-center justify-center size-6 rounded-3 bg-accent-bg text-accent shrink-0">
          {icon}
        </span>
      )}
      <div className="min-w-0">
        <h1 className="text-title truncate" title={titleTooltip}>
          {title}
        </h1>
        <p className="text-meta text-muted">{context}</p>
      </div>
      {actions === undefined ? null : (
        <div className="ml-auto flex gap-2">{actions}</div>
      )}
    </header>
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
