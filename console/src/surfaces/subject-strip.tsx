import type { ReactNode } from 'react';

import NextLink from 'next/link';

import { Badge, StatusDot } from '@/components/status';
import { cx } from '@/design/cx';
import { statusPresentation } from '@/design/status';
import { formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { SUBJECT_WINDOW_HOURS, type IncidentGroup } from './incident-groups';
import { RecurrenceStrip, SubjectLine, subjectTitle } from './incident-group-list';

/**
 * "O que insiste em acontecer": one compact row per recurring subject in the
 * trailing window, live ones first -- the Painel's own denser reading of the
 * groups `groupBySubject` already produces, next to `IncidentGroupList`'s
 * full `<details>` disclosure rather than replacing it. `dashboard.tsx`
 * supplies groups already windowed (`subjectsInWindow`) and filtered to
 * recurring ones (`count > 1`); this component only orders and draws them.
 */

/**
 * How many rows the strip draws before the rest are behind its own link.
 *
 * The artboard draws five and names the total beside them, which is the
 * shape every other list on this page already has: six run cards, eight
 * activity entries, five subjects.
 */
export const SUBJECT_VISIBLE_MAX = 5;

/**
 * How wide every row's firing timeline is, in the units its own `viewBox`
 * counts.
 *
 * Fixed, and the same for every row, because the window is the same window
 * for all of them: a strip sized from its own firing count gives a subject
 * that fired twice a twelve-pixel axis, on which "an hour apart" and "two
 * days apart" are the same picture, and puts two rows on two different
 * scales so neither can be read against the other.
 */
const SUBJECT_TIMELINE_WIDTH = 120;

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
  return (
    <NextLink
      href={rowHref(group)}
      data-testid="subject-row"
      data-live={group.live ? 'true' : 'false'}
      // Two treatments, because the two rows mean different things. A subject
      // still firing sits on its own surface with a border around it; one
      // that is over sits flat on the panel, and its name gives up the
      // emphasis. Drawn identically, the only thing separating "this is
      // happening" from "this happened" was the chip at the far right of a
      // row the reader had already stopped scanning.
      className={cx(
        'flex items-center gap-3 rounded-2 px-2 py-2 motion-hover hover:bg-sunken min-w-0 edge',
        group.live ? 'bg-sunken border-border' : 'border-transparent',
      )}
      {...(subjectTitle(group, subjectNames) === undefined
        ? {}
        : { title: subjectTitle(group, subjectNames) })}
    >
      {/* What this row is, before what it says: the severity while the
          subject is still firing, the outcome once it is over. The same
          reading `IncidentGroupList` already makes of a group -- severity is
          an alarm, and an alarm that ended is history rather than a colour
          still shouting. */}
      <span data-testid="subject-mark" className="shrink-0">
        <StatusDot status={group.live ? group.severity : group.state} />
      </span>
      <div className="flex flex-col gap-1 min-w-0">
        <span
          data-testid="subject-title"
          className={cx(
            'text-small font-medium truncate',
            group.live ? '' : 'text-muted',
          )}
        >
          {group.title}
        </span>
        <span data-testid="subject-subtitle" className="text-meta text-muted truncate">
          <SubjectLine group={group} subjectNames={subjectNames} />
        </span>
      </div>
      <span className="ml-auto shrink-0" data-testid="subject-timeline">
        <RecurrenceStrip
          group={group}
          now={now}
          windowHours={SUBJECT_WINDOW_HOURS}
          width={SUBJECT_TIMELINE_WIDTH}
        />
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
      {liveFirst(groups)
        .slice(0, SUBJECT_VISIBLE_MAX)
        .map((group) => (
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
