import type { ReactNode } from 'react';

import { cx } from '@/design/cx';
import { message, type Locale } from '@/i18n/messages';

/**
 * "Atividade ao vivo": a vertical timeline of what the deployment did, each
 * entry carrying the shape of its own kind rather than a shared,
 * undifferentiated dot -- the defect the audit named directly ("Recent
 * activity" repeating the same incident five times with no shape or
 * hierarchy). Four kinds, four shapes, `Main.dc.html`'s own vocabulary: a
 * diamond for an investigation starting, a circle for one resolving (an
 * incident closing on its own reads the same way -- both are something
 * ending well), a square for an incident opening, a triangle for a decision
 * (proposed or decided). Colour is the outcome underneath the shape, never
 * the only carrier of it.
 *
 * `dashboard.tsx` builds `entries` from three already-read listings (runs,
 * incidents, approvals/proposals) and folds repeated firings of the same
 * subject with `collapseFeed` before handing them here; this component only
 * draws what it is given, newest first.
 */

export type ActivityFeedKind = 'investigation' | 'resolution' | 'incident' | 'approval';

/** The glyph for each kind, over the frozen `icon-inline` glyph scale. */
const KIND_MARK: Readonly<Record<ActivityFeedKind, string>> = {
  investigation: 'icon-inline rotate-45 rounded-1',
  resolution: 'icon-inline rounded-full',
  incident: 'icon-inline rounded-1',
  approval: 'icon-inline clip-triangle',
};

export type ActivityFeedOutcome = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

const OUTCOME_FILL: Readonly<Record<ActivityFeedOutcome, string>> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
  neutral: 'bg-neutral',
};

/** One thing the deployment did, or one thing waiting on somebody. */
export interface ActivityFeedEntry {
  readonly id: string;
  readonly kind: ActivityFeedKind;
  readonly outcome: ActivityFeedOutcome;
  readonly title: string;
  readonly detail: string;
  readonly href: string;
  readonly relative: string;
  readonly absolute: string;
  readonly iso: string;
  /** The correlation key repeated firings collapse by -- '' for anything
   * `collapseFeed` never folds (an investigation, a decision). */
  readonly subjectKey: string;
  /** How many consecutive firings of the same subject this entry already
   * folds -- 1 for an entry `collapseFeed` has not touched. */
  readonly count: number;
  /**
   * What produced this entry, in the viewer's language -- the board's own
   * middle term on the second line (`agora mesmo · manual`,
   * `há 50 min · Alertmanager`, `há 29 min · sem intervenção humana`).
   *
   * Read from what the entry's own source already served, never composed
   * here: a run's trigger, an incident's detector, the fact that a closure
   * had no human in it. Empty when the source named nothing, in which case
   * the second line is the instant alone rather than a word invented to fill
   * the slot.
   */
  readonly kindLabel: string;
  /**
   * How long the work behind the entry took, already formatted -- empty for
   * an entry with no duration to report.
   *
   * Only a settled run has one: it is the distance between the two instants
   * the runs listing already carries. An incident opening, a decision being
   * proposed and a closure are moments rather than spans, and none of them
   * gets a fabricated one.
   */
  readonly duration: string;
}

/**
 * Fold adjacent `incident`-kind entries that share a `subjectKey` into one,
 * carrying a count -- the real defect the audit named
 * (`DNSResolverProbeFailed` five times over, indistinguishable rows).
 *
 * Only *adjacent* entries collapse. Two firings of the same subject with
 * something else between them in the sorted feed are two separate moments in
 * the narrative, not one the reader should be told happened once -- and
 * entries with an empty `subjectKey` (an investigation starting, a decision)
 * never fold into one another regardless of kind.
 */
export function collapseFeed(
  entries: readonly ActivityFeedEntry[],
): readonly ActivityFeedEntry[] {
  const collapsed: ActivityFeedEntry[] = [];
  for (const entry of entries) {
    const last = collapsed[collapsed.length - 1];
    if (
      last !== undefined &&
      entry.kind === 'incident' &&
      last.kind === 'incident' &&
      entry.subjectKey !== '' &&
      entry.subjectKey === last.subjectKey
    ) {
      collapsed[collapsed.length - 1] = { ...last, count: last.count + entry.count };
      continue;
    }
    collapsed.push(entry);
  }
  return collapsed;
}

export interface ActivityFeedProps {
  readonly locale: Locale;
  readonly entries: readonly ActivityFeedEntry[];
}

/** "Atividade ao vivo": newest first, each entry shaped by its own kind.
 *
 * A flex row per entry -- the shape beside the text, never behind it on an
 * absolutely-positioned rail -- because a connecting line drawn precisely
 * through the centre of four differently-shaped marks needs an off-scale
 * pixel offset for each one, and every spacing value here comes from the
 * declared scale with no exception carved out for a decoration.
 */
export function ActivityFeed({ locale, entries }: ActivityFeedProps): ReactNode {
  return (
    <ol className="flex flex-col">
      {entries.map((entry) => (
        <li
          key={entry.id}
          data-testid="activity-feed-entry"
          data-kind={entry.kind}
          className="slide-in edge border-border border-x-0 border-t-0 last:border-b-0"
        >
          <a
            href={entry.href}
            className="flex items-start gap-3 py-2 motion-hover hover:opacity-90"
          >
            <span
              aria-hidden="true"
              className={cx(
                'mt-1 shrink-0',
                KIND_MARK[entry.kind],
                OUTCOME_FILL[entry.outcome],
              )}
            />
            <span className="min-w-0 flex flex-col gap-1">
              <span className="text-small">
                <span className="font-medium">{entry.title}</span>
                {entry.detail === '' ? null : <> — {entry.detail}</>}
                {entry.count > 1 ? (
                  <span
                    data-testid="activity-feed-count"
                    className="text-meta text-muted ml-1"
                  >
                    {message(locale, 'dashboard.liveActivity.count', {
                      count: String(entry.count),
                    })}
                  </span>
                ) : null}
              </span>
              <time
                dateTime={entry.iso}
                title={entry.absolute}
                className="text-meta text-muted"
              >
                {entry.relative}
              </time>
            </span>
          </a>
        </li>
      ))}
    </ol>
  );
}
