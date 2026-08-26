import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { AlertTriangleIcon, ArrowRightIcon } from '@/design/icons';

/**
 * What is waiting on a person, above everything else on the page.
 *
 * The order down the overview is the order of urgency and it is fixed: this
 * block sits above the statistics because a number is never more urgent than a
 * decision somebody is waiting on. It is danger-bordered, it says how many and
 * how old the oldest is, and every row reaches its subject in one click — a
 * queue that takes three navigations to act on is a queue people work around.
 *
 * It is absent when it is empty rather than showing a cheerful nothing. The
 * empty case is a panel of its own on the overview, because "nothing is waiting"
 * is worth saying once and not worth a danger border.
 */

/** One thing waiting on a person, as a row of the block. */
export interface AttentionRow {
  readonly id: string;
  /** Approval, question, incident, failure — the word a reader sees. */
  readonly kind: string;
  readonly title: string;
  /** Everything after the title on the row: state, risk class, what is at stake. */
  readonly detail: string;
  readonly href: string;
  /** How long it has been waiting, already phrased. */
  readonly since: string;
  /** The source instant used to decide which row has waited longest. */
  readonly at?: string;
}

/**
 * How many rows the block draws before it stops.
 *
 * A list whose length nothing bounds is grouped or paged, never dumped — and
 * this block was the worst offender on the console, because the rows it dumps
 * are the ones it most wants read. Sixteen of them is a page nobody reads to
 * the end of, and what that costs is precisely the rows at the bottom: the
 * oldest, which is to say the ones that have been waiting longest.
 *
 * Six, because the block sits above the fold and has to leave the page below
 * it visible. It is a drawing decision and nothing else — the heading still
 * counts the whole queue, and the overflow row reaches every row this one
 * did not draw.
 */
export const ATTENTION_ROWS_SHOWN = 6;

export interface AttentionBlockProps {
  readonly heading: string;
  /** "Oldest 2h 14m", already phrased. */
  readonly oldest: string;
  readonly rows: readonly AttentionRow[];
  readonly openLabel: string;
  /** What the overflow row says, given how many rows were not drawn. */
  readonly moreLabel: (over: number) => string;
  /** Where the overflow row goes: the list holding all of them. */
  readonly moreHref: string;
}

/** The danger-bordered block at the top of the overview. */
export function AttentionBlock({
  heading,
  oldest,
  rows,
  openLabel,
  moreLabel,
  moreHref,
}: AttentionBlockProps): ReactNode {
  if (rows.length === 0) {
    return null;
  }
  const shown = rows.slice(0, ATTENTION_ROWS_SHOWN);
  const over = rows.length - shown.length;
  return (
    <section
      data-testid="attention"
      aria-label={heading}
      className="rounded-3 edge border-danger bg-danger-bg mb-5"
    >
      <header className="flex items-center gap-2 px-4 py-3">
        <span className="text-danger" aria-hidden="true">
          <AlertTriangleIcon />
        </span>
        <h2 className="text-section text-danger">{heading}</h2>
        {/* Not shouted in capitals: this says which of the rows below has
            been waiting longest, which is the reason to look at this row
            first rather than decoration on top of the count. */}
        <span className="ml-auto text-micro text-muted edge border-border-strong rounded-1 px-2">
          {oldest}
        </span>
      </header>
      <ul className="flex flex-col">
        {shown.map((row) => (
          <li key={row.id} data-testid="attention-row" data-kind={row.kind}>
            <a
              href={row.href}
              className="flex items-center gap-3 px-4 py-3 bg-raised edge border-border border-x-0 border-b-0 motion-hover hover:bg-hover"
            >
              <Badge status={row.kind} />
              <span className="min-w-0 flex flex-col">
                <span className="text-strong truncate">{row.title}</span>
                <span className="text-meta text-muted truncate">
                  {row.detail} · {row.since}
                </span>
              </span>
              <span className="ml-auto text-muted" aria-hidden="true">
                <ArrowRightIcon />
              </span>
              <span className="sr-only">{openLabel}</span>
            </a>
          </li>
        ))}
        {over === 0 ? null : (
          <li>
            <a
              href={moreHref}
              data-testid="attention-more"
              className="flex items-center gap-3 px-4 py-3 bg-raised edge border-border border-x-0 border-b-0 text-small motion-hover hover:bg-hover"
            >
              {moreLabel(over)}
              <span className="ml-auto text-muted" aria-hidden="true">
                <ArrowRightIcon />
              </span>
            </a>
          </li>
        )}
      </ul>
    </section>
  );
}
