import type { ReactNode } from 'react';

import NextLink from 'next/link';

import { Badge } from '@/components/status';
import { statusPresentation } from '@/design/status';
import { formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import type { IncidentGroup } from './incident-groups';
import { RecurrenceStrip, SubjectLine, subjectTitle } from './incident-group-list';

/**
 * "O que insiste em acontecer": one compact row per recurring subject in the
 * trailing window, live ones first -- the Painel's own denser reading of the
 * groups `groupBySubject` already produces, next to `IncidentGroupList`'s
 * full `<details>` disclosure rather than replacing it. `dashboard.tsx`
 * supplies groups already windowed (`subjectsInWindow`) and filtered to
 * recurring ones (`count > 1`); this component only orders and draws them.
 */

export interface SubjectStripProps {
  readonly locale: Locale;
  readonly now: Date;
  readonly groups: readonly IncidentGroup[];
  /**
   * The estate's own name for a subject, when the page already resolved
   * one -- the same optional, resolved-once-for-the-page map
   * `IncidentGroupList` takes, so a row never shows a name this component
   * invented.
   */
  readonly subjectNames?: ReadonlyMap<string, string>;
}

/** Live groups first; ties keep `groupBySubject`'s own order (severity, then
 * recency), which this never re-sorts within either half. */
function liveFirst(groups: readonly IncidentGroup[]): readonly IncidentGroup[] {
  const live = groups.filter((group) => group.live);
  const settled = groups.filter((group) => !group.live);
  return [...live, ...settled];
}

/** Where the row's title links: the linked investigation of the newest
 * firing that has one running, or the newest firing's own public address
 * otherwise -- never a hex id, and never the group's own synthetic key. */
function rowHref(group: IncidentGroup): string {
  const running = group.occurrences.find(
    (occurrence) => occurrence.runId !== '' && occurrence.state !== 'resolved',
  );
  if (running !== undefined) return `/runs?selected=${running.runId}`;
  const newest = group.occurrences[0];
  return `/incidents?selected=${newest?.publicId ?? ''}`;
}

function SubjectRow({
  group,
  locale,
  now,
  subjectNames,
}: {
  readonly group: IncidentGroup;
  readonly locale: Locale;
  readonly now: Date;
  readonly subjectNames: ReadonlyMap<string, string>;
}): ReactNode {
  void now; // reserved for a "recorrente desde" relative label a follow-up can add
  return (
    <NextLink
      href={rowHref(group)}
      data-testid="subject-row"
      className="flex items-center gap-3 rounded-2 px-2 py-2 motion-hover hover:bg-sunken min-w-0"
      {...(subjectTitle(group, subjectNames) === undefined
        ? {}
        : { title: subjectTitle(group, subjectNames) })}
    >
      <div className="flex flex-col gap-1 min-w-0">
        <span className="text-small font-medium truncate">{group.title}</span>
        <span
          data-testid="subject-subtitle"
          className="text-meta text-muted truncate"
        >
          <SubjectLine group={group} subjectNames={subjectNames} />
        </span>
      </div>
      <span className="ml-auto shrink-0" data-testid="subject-timeline">
        <RecurrenceStrip group={group} />
      </span>
      <span
        data-testid="subject-chip"
        data-role={statusPresentation(group.state).role}
        className="shrink-0"
      >
        <Badge status={group.state} />
      </span>
      <span
        className="font-mono text-meta text-muted shrink-0"
        data-testid="subject-count"
      >
        {formatNumber(locale, group.count)}×
      </span>
    </NextLink>
  );
}

/** The recurring-subjects strip: live first, each with its own timeline. */
export function SubjectStrip({
  locale,
  now,
  groups,
  subjectNames,
}: SubjectStripProps): ReactNode {
  if (groups.length === 0) {
    return (
      <div className="flex flex-col gap-2 items-start">
        <p className="text-small text-muted">
          {message(locale, 'dashboard.subjects.empty')}
        </p>
        <NextLink href="/incidents" className="text-accent hover:underline text-small">
          {message(locale, 'dashboard.subjects.empty.action')}
        </NextLink>
      </div>
    );
  }
  const names = subjectNames ?? new Map<string, string>();
  return (
    <div className="flex flex-col gap-1 min-w-0">
      {liveFirst(groups).map((group) => (
        <SubjectRow
          key={group.key}
          group={group}
          locale={locale}
          now={now}
          subjectNames={names}
        />
      ))}
    </div>
  );
}
