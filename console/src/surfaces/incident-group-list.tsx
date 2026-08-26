import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { cx } from '@/design/cx';
import { formatCount, formatNumber, timestamp } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import type { IncidentGroup } from './incident-groups';

/**
 * One row per cause, and every firing of it one disclosure away.
 *
 * The flat listing was not merely long, it was untrue: an estate raising seven
 * conditions all day produced fifty rows, and a reader scrolling them was
 * being told there were fifty problems. This says seven, with a count beside
 * each, and keeps every individual firing reachable rather than summarised
 * away — a recurrence is evidence, and a count with nothing behind it is a
 * number nobody can check.
 *
 * The disclosure is `<details>`, which is the whole reason this renders on the
 * server. It opens and closes with no JavaScript, it is in the tab order and
 * answers the space bar without anybody wiring that up, and it announces its
 * own expanded state. A `<div>` with a click handler would have needed all
 * three written by hand and would have had none of them until somebody
 * noticed.
 */

export interface IncidentGroupListProps {
  readonly groups: readonly IncidentGroup[];
  readonly locale: Locale;
  /** The instant relative times are read against, as the server resolved it. */
  readonly now: Date;
  readonly zone: string;
}

/** The grouped listing. */
export function IncidentGroupList({
  groups,
  locale,
  now,
  zone,
}: IncidentGroupListProps): ReactNode {
  const firings = groups.reduce((total, group) => total + group.count, 0);
  return (
    <div data-testid="incident-groups">
      <p className="text-meta text-muted pb-3">
        {message(locale, 'incidents.group.summary', {
          subjects: formatNumber(locale, groups.length),
          firings: formatNumber(locale, firings),
        })}
      </p>
      <ul className="flex flex-col">
        {groups.map((group) => {
          const last = timestamp(locale, group.lastAt, now, zone);
          const first = timestamp(locale, group.firstAt, now, zone);
          return (
            <li
              key={group.key}
              data-testid="incident-group"
              data-live={group.live ? 'true' : 'false'}
              data-count={group.count}
              className="edge border-border border-x-0 border-t-0 last:border-b-0"
            >
              <details className="group">
                <summary
                  data-testid="incident-group-summary"
                  className={cx(
                    'flex items-center gap-3 py-3 cursor-pointer list-none',
                    'motion-hover hover:bg-hover',
                  )}
                >
                  {/* The marker is drawn rather than left to the browser: the
                      default triangle differs on every platform and cannot be
                      given the muted colour the rest of the row is in. */}
                  <span
                    aria-hidden="true"
                    className="text-muted shrink-0 motion-hover group-open:rotate-90"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="icon-nav"
                    >
                      <path d="m9 6 6 6-6 6" />
                    </svg>
                  </span>
                  <span className="min-w-0 flex flex-col">
                    <span className="text-strong truncate">{group.title}</span>
                    <span className="text-meta text-muted truncate">
                      {group.subjects.length === 0
                        ? group.detector
                        : group.subjects.join(' · ')}
                    </span>
                  </span>
                  <Badge status={group.severity} className="ml-auto shrink-0" />
                  <Badge status={group.state} className="shrink-0" />
                  <span
                    data-testid="incident-group-count"
                    className="text-small tabular-nums text-right shrink-0 w-column-measure"
                  >
                    {formatCount(
                      locale,
                      group.count,
                      'incidents.group.count.one',
                      'incidents.group.count',
                    )}
                  </span>
                  <span className="text-small text-muted tabular-nums text-right shrink-0 w-column-instant">
                    <time dateTime={group.lastAt} title={last.absolute}>
                      {last.relative}
                    </time>
                  </span>
                  <span className="sr-only">
                    {message(locale, 'incidents.group.expand', { title: group.title })}
                  </span>
                </summary>

                <div className="pb-3 pl-6">
                  {group.count > 1 ? (
                    <p className="text-meta text-muted pb-2">
                      {message(locale, 'incidents.group.since', {
                        since: first.relative,
                      })}
                    </p>
                  ) : null}
                  <ul className="flex flex-col">
                    {group.occurrences.map((one) => {
                      const at = timestamp(locale, one.at, now, zone);
                      return (
                        <li
                          key={one.id}
                          data-testid="incident-occurrence"
                          className="edge border-border border-x-0 border-t-0 last:border-b-0"
                        >
                          <a
                            href={`/incidents/${one.publicId}`}
                            className="flex items-center gap-3 py-2 motion-hover hover:opacity-90"
                          >
                            <span className="text-small min-w-0 truncate">
                              {one.summary === '' ? one.publicId : one.summary}
                            </span>
                            <Badge status={one.state} className="ml-auto shrink-0" />
                            <span className="text-meta text-muted tabular-nums text-right shrink-0 w-column-instant">
                              <time dateTime={one.at} title={at.absolute}>
                                {at.relative}
                              </time>
                            </span>
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
