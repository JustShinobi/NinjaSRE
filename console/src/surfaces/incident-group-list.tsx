import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { cx } from '@/design/cx';
import { formatCount, formatNumber, timestamp } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import type { IncidentGroup } from './incident-groups';
import { DEFAULT_TIMELINE_WINDOW_HOURS, positionOnTimeline } from './incident-timeline';

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
 *
 * The closed row is still reachable in one click, without opening anything:
 * the title itself is a link to the newest firing's own page, so the row
 * carries `data-testid="row"` the same as every other "now" screen's list —
 * `RowList` puts the link on its first cell, this puts it on the title inside
 * `<summary>`, which stays in the accessibility tree whether the disclosure
 * is open or closed.
 */

export interface IncidentGroupListProps {
  readonly groups: readonly IncidentGroup[];
  readonly locale: Locale;
  /** The instant relative times are read against, as the server resolved it. */
  readonly now: Date;
  readonly zone: string;
  /**
   * A headline per run id, resolved once for the whole page rather than once
   * per row — the "last cause found" block reads this map instead of making
   * its own request.
   *
   * Optional, and empty when absent: a caller that never fetched runs (the
   * dashboard's own mini-timeline, which is a different feature's screen)
   * still gets a correct render, with no "last cause found" block on any
   * row instead of a prop it would have had to fabricate.
   */
  readonly runHeadlines?: ReadonlyMap<string, string>;
  /**
   * The estate's own name for every subject this page already resolved it
   * for, keyed by the id the subject is carried as — the same "resolved once
   * for the whole page, never per row" shape as `runHeadlines`.
   *
   * Optional, and empty when absent: a caller that never fetched the estate
   * still gets a correct render — an opaque subject with no name in the map
   * renders nothing rather than its own id (FR-024/SC-007 ban that
   * unconditionally, not only while unresolved), and a subject that was
   * already a name keeps reading exactly as it did before this map existed.
   */
  readonly subjectNames?: ReadonlyMap<string, string>;
}

/** How much of an opaque identifier is enough to recognise it by. */
const IDENTIFIER_HEAD = 8;

/**
 * Whether `subject` is an identifier rather than a name somebody chose.
 *
 * A long unbroken run of hexadecimal after a short prefix is a key, not a
 * hostname: `res-7a73b8aa1194c1ed14dd87f7e0e80b81` identifies the row for a
 * database and for nobody else. `adguard-primary` is a name and is left alone —
 * the test is the shape of the string, never a list of prefixes this file
 * would have to keep in step with whatever the gateway starts sending.
 */
export function isOpaque(subject: string): boolean {
  const tail = subject.slice(subject.indexOf('-') + 1);
  return subject.includes('-') && tail.length >= 24 && /^[0-9a-f]+$/u.test(tail);
}

/** `subject`, shortened when it is a key and untouched when it is a name. */
export function shortenIdentifier(subject: string): string {
  if (!isOpaque(subject)) return subject;
  const prefix = subject.slice(0, subject.indexOf('-') + 1);
  return `${prefix}${subject.slice(prefix.length, prefix.length + IDENTIFIER_HEAD)}…`;
}

/**
 * The estate's own name for `subject`, when it taught this page one.
 *
 * `undefined` both when nothing resolved it and when the gateway's own
 * fallback echoed the id back as the name (`display_name or resource_id`,
 * in the estate route) — neither is a name gained, and printing the id
 * twice under two labels is not the fix this screen owes.
 */
export function resolvedName(
  subject: string,
  subjectNames: ReadonlyMap<string, string>,
): string | undefined {
  const found = subjectNames.get(subject);
  return found !== undefined && found !== subject ? found : undefined;
}

/**
 * The full subject line, offered only where the visible one differs from
 * it -- a subject renamed, or an opaque one left out of the visible line
 * altogether.
 */
export function subjectTitle(
  group: IncidentGroup,
  subjectNames: ReadonlyMap<string, string>,
): string | undefined {
  const changed = group.subjects.some(
    (subject) => isOpaque(subject) || resolvedName(subject, subjectNames) !== undefined,
  );
  return changed ? group.subjects.join(' · ') : undefined;
}

/** The newest occurrence's short address — `groupBySubject` orders newest first. */
function newestPublicId(group: IncidentGroup): string {
  return group.occurrences[0]?.publicId ?? '';
}

/** The newest occurrence that has not ended, when the group is currently live. */
function speakingOccurrence(
  group: IncidentGroup,
): IncidentGroup['occurrences'][number] | undefined {
  return group.occurrences.find(
    (occurrence) => occurrence.runId !== '' && !isSettled(occurrence.state),
  );
}

const SETTLED_STATES = new Set(['resolved', 'closed', 'suppressed']);

function isSettled(state: string): boolean {
  return SETTLED_STATES.has(state);
}

/** The newest settled occurrence carrying a run — the "last cause found" block's subject. */
function lastSettledWithRun(
  group: IncidentGroup,
): IncidentGroup['occurrences'][number] | undefined {
  return group.occurrences.find(
    (occurrence) => occurrence.runId !== '' && isSettled(occurrence.state),
  );
}

/**
 * One severity/subject line, reading left to right: the estate's name for a
 * subject when this page has one, an already-human subject exactly as it
 * arrived, and an *opaque* identifier with no resolved name left out of the
 * line altogether — never printed, not even shortened. FR-024/SC-007 permit
 * an internal identifier at most as this row's own tooltip, never as its
 * text, and that holds whether or not a name was ever found for one: the
 * fix that first built this map still let a resolved name's own id trail it
 * as visible text ("pve01 · res-76ab1466…"), which is the identical shape
 * one word later. The full, un-shortened subject list still reaches a
 * reader through this row's own `title` (`subjectTitle`), which is where an
 * identifier belongs at most.
 *
 * A short id that was never opaque to begin with (`ct-102`) is a different
 * case: naming it beside the resolved name it gained (`anchor`) does not
 * print anything SC-007 bans, so it keeps trailing the name as a detail,
 * exactly as before — `isOpaque` is the one test this file uses to decide
 * what counts as "internal" everywhere else, and this keeps agreeing with
 * it rather than drawing a second line.
 */
export function SubjectLine({
  group,
  subjectNames,
}: {
  readonly group: IncidentGroup;
  readonly subjectNames: ReadonlyMap<string, string>;
}): ReactNode {
  const readable = group.subjects
    .map((subject) => ({ subject, name: resolvedName(subject, subjectNames) }))
    // An opaque subject nobody has named is left out of the visible line
    // entirely rather than shown shortened.
    .filter(({ subject, name }) => name !== undefined || !isOpaque(subject));
  if (readable.length === 0) {
    return <>{group.detector}</>;
  }
  return (
    <>
      {readable.map(({ subject, name }, index) => (
        <span key={subject}>
          {index > 0 ? ' · ' : ''}
          {name === undefined ? (
            subject
          ) : (
            <span data-testid="incident-subject-name" data-resource-id={subject}>
              {name}
              {isOpaque(subject) ? null : (
                <span className="font-mono text-muted">{` · ${subject}`}</span>
              )}
            </span>
          )}
        </span>
      ))}
    </>
  );
}

/**
 * One vertical bar per occurrence, height/opacity rising toward the most
 * recent.
 *
 * `now` switches the bars from evenly-spaced ordinal rank to real position
 * inside `windowHours`, via `positionOnTimeline` -- the same function
 * `TwentyFourHourStrip` below uses for its own axis. Omitted, the strip
 * keeps the ordinal, evenly-spaced layout unchanged: the Incidents screen's
 * own compact row (below, in `IncidentGroupList`) leaves `now` unset, since
 * its own expansion already draws an accurate proportional axis and does
 * not need a second one in the collapsed row. The Painel's "what insists"
 * strip passes both, because two firings an hour apart must read as closer
 * together than two firings twelve hours apart, and ordinal rank cannot
 * tell those two cases apart.
 *
 * `width` fixes the axis every bar is placed on. Left unset the strip is as
 * wide as its own firing count needs, which is what an ordinal row wants and
 * exactly what a real timeline must not have: an axis whose length varies per
 * row puts two rows on two scales, and twelve pixels is not enough of one to
 * tell an hour from a day.
 */
export function RecurrenceStrip({
  group,
  now,
  windowHours = DEFAULT_TIMELINE_WINDOW_HOURS,
  width: fixedWidth,
}: {
  readonly group: IncidentGroup;
  readonly now?: Date;
  readonly windowHours?: number;
  readonly width?: number;
}): ReactNode {
  if (group.occurrences.length <= 1) return null;
  const oldestFirst = [...group.occurrences].reverse();
  const barWidth = 3;
  const width = fixedWidth ?? oldestFirst.length * 6;
  // The ordinal fallback's own step: the six pixels a self-sized strip has
  // always used, or the axis divided evenly when the width was fixed from
  // outside and there is no instant to place a bar by.
  const step =
    fixedWidth === undefined
      ? 6
      : (width - barWidth) / Math.max(oldestFirst.length - 1, 1);
  // The left edge travels the whole `[0, width - barWidth]` range as a
  // direct linear function of `percent`, so the newest bar's right edge
  // lands exactly on `width` and the oldest bar's left edge exactly on `0`
  // -- never clamped, which would collapse two occurrences both near `now`
  // onto the same pixel and erase the exact distinction this exists to draw.
  const byInstant =
    now === undefined
      ? undefined
      : new Map(
          positionOnTimeline(group.occurrences, now, windowHours).points.map(
            (point) => [point.id, point.percent] as const,
          ),
        );
  return (
    <svg
      data-testid="incident-recurrence-strip"
      viewBox={`0 0 ${String(width)} 16`}
      width={width}
      height={16}
      aria-hidden="true"
      className={cx('shrink-0', group.live ? 'text-danger' : 'text-muted')}
    >
      {oldestFirst.map((occurrence, index) => {
        const percent = byInstant?.get(occurrence.id);
        const x =
          percent === undefined ? index * step : (percent / 100) * (width - barWidth);
        return (
          <rect
            key={occurrence.id}
            x={x}
            y={16 - (6 + index * (10 / Math.max(oldestFirst.length - 1, 1)))}
            width={barWidth}
            height={6 + index * (10 / Math.max(oldestFirst.length - 1, 1))}
            rx={1.5}
            fill="currentColor"
            opacity={0.35 + (0.65 * index) / Math.max(oldestFirst.length - 1, 1)}
          />
        );
      })}
    </svg>
  );
}

/** The 24h axis, one point per occurrence inside the window. */
function TwentyFourHourStrip({
  group,
  locale,
  now,
  zone,
}: {
  readonly group: IncidentGroup;
  readonly locale: Locale;
  readonly now: Date;
  readonly zone: string;
}): ReactNode {
  const timeline = positionOnTimeline(group.occurrences, now);
  if (timeline.points.length === 0) return null;
  const start = timestamp(locale, timeline.windowStart, now, zone);
  return (
    <div className="flex flex-col gap-2" data-testid="incident-24h-strip">
      <span className="text-micro text-muted font-medium uppercase tracking-wide">
        {message(locale, 'incidents.timeline.title')}
      </span>
      <div className="relative rounded-2 bg-sunken edge border-border px-3 py-3">
        <span
          aria-hidden="true"
          className="absolute left-3 right-3 top-1/2 h-px -translate-y-1/2 bg-border"
        />
        {timeline.points.map((point) => {
          const at = timestamp(locale, point.at, now, zone);
          return (
            <span
              key={point.id}
              data-testid="incident-24h-point"
              data-shape={point.shape}
              title={`${at.absolute} — ${point.state}`}
              className={cx(
                'absolute top-1/2 -translate-y-1/2 -translate-x-1/2',
                point.shape === 'diamond'
                  ? 'icon-inline rotate-45 bg-accent'
                  : 'icon-inline rounded-full bg-success',
              )}
              style={{ left: `${String(point.percent)}%` }}
            />
          );
        })}
        <span className="absolute left-3 -bottom-4 text-micro text-muted">
          {start.absolute}
        </span>
        <span className="absolute right-3 -bottom-4 text-micro text-muted">
          {message(locale, 'incidents.timeline.now')}
        </span>
      </div>
      {timeline.overflowCount > 0 ? (
        <p className="text-micro text-muted pt-1">
          {message(locale, 'incidents.timeline.overflow', {
            count: formatNumber(locale, timeline.overflowCount),
          })}
        </p>
      ) : null}
    </div>
  );
}

/** "Investigation in progress" and "last cause found", from data the page already fetched. */
function CauseBlock({
  group,
  locale,
  runHeadlines,
}: {
  readonly group: IncidentGroup;
  readonly locale: Locale;
  readonly runHeadlines: ReadonlyMap<string, string>;
}): ReactNode {
  const speaking = group.live ? speakingOccurrence(group) : undefined;
  const settled = lastSettledWithRun(group);
  const headline = settled !== undefined ? runHeadlines.get(settled.runId) : undefined;

  if (speaking === undefined && (settled === undefined || headline === undefined)) {
    return null;
  }

  return (
    <div className="flex items-center gap-3 mt-2">
      {settled !== undefined && headline !== undefined ? (
        <div className="flex items-center gap-2 rounded-2 bg-accent-bg edge border-border px-3 py-2 flex-1 min-w-0">
          <span
            className="h-2 w-2 rounded-full bg-success shrink-0"
            aria-hidden="true"
          />
          <span className="text-small min-w-0 truncate">
            <span className="text-strong">
              {message(locale, 'incidents.cause.found')}
            </span>{' '}
            {headline}
          </span>
        </div>
      ) : null}
      {speaking !== undefined ? (
        <a
          href={`/runs/${speaking.runId}`}
          data-testid="incident-live-link"
          className="text-small shrink-0 flex items-center gap-2 text-accent hover:underline"
        >
          {message(locale, 'incidents.cause.live')}
        </a>
      ) : null}
    </div>
  );
}

/** The grouped listing. */
export function IncidentGroupList({
  groups,
  locale,
  now,
  zone,
  runHeadlines = new Map(),
  subjectNames = new Map(),
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
              data-testid="row"
              data-row={group.key}
              className="edge border-border border-x-0 border-t-0 last:border-b-0"
            >
              <details
                className="group"
                data-testid="incident-group"
                data-live={group.live ? 'true' : 'false'}
                data-count={group.count}
              >
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
                  <span
                    aria-hidden="true"
                    className={cx(
                      'icon-inline shrink-0',
                      group.live ? 'bg-danger' : 'bg-success',
                    )}
                  />
                  <span className="min-w-0 flex flex-col">
                    {/* The one-click reach to this subject's own page, always
                        in the accessibility tree — `<summary>`'s own content
                        never hides, whether the disclosure is open or
                        closed. */}
                    <a
                      href={`/incidents/${newestPublicId(group)}`}
                      data-testid="incident-group-title-link"
                      className="text-strong truncate hover:underline"
                    >
                      {group.title}
                    </a>
                    <span
                      data-testid="incident-group-subjects"
                      className="text-meta text-muted truncate"
                      {...(subjectTitle(group, subjectNames) === undefined
                        ? {}
                        : { title: subjectTitle(group, subjectNames) })}
                    >
                      <SubjectLine group={group} subjectNames={subjectNames} />
                    </span>
                  </span>
                  <RecurrenceStrip group={group} />
                  {/* Severity yields to state once a cause is over. Fifteen
                      rows reading "Critical" in danger red beside a quiet green
                      "Resolved" made the alarm the loudest thing on a screen
                      where nothing was currently wrong. It is still said — a
                      critical that resolved is not a low one that resolved —
                      but as history rather than as an alarm. */}
                  <span
                    data-testid="incident-group-severity"
                    data-past={group.live ? 'false' : 'true'}
                    className="ml-auto shrink-0"
                  >
                    {group.live ? (
                      <Badge status={group.severity} />
                    ) : (
                      // No `capitalize`: it title-cases every word, and "Was
                      // Critical" reads as a proper noun rather than as the
                      // aside it is.
                      <span className="text-meta text-muted">
                        {message(locale, 'incidents.group.wasSeverity', {
                          severity: group.severity,
                        })}
                      </span>
                    )}
                  </span>
                  <span data-testid="incident-group-state" className="shrink-0">
                    <Badge status={group.state} />
                  </span>
                  <span
                    data-testid="incident-group-count"
                    className="text-small tabular-nums text-right shrink-0 w-column-measure font-mono"
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

                <div className="pb-4 pl-6 pr-2 flex flex-col gap-3">
                  {group.count > 1 ? (
                    <p className="text-meta text-muted">
                      {message(locale, 'incidents.group.since', {
                        since: first.relative,
                      })}
                    </p>
                  ) : null}
                  <TwentyFourHourStrip
                    group={group}
                    locale={locale}
                    now={now}
                    zone={zone}
                  />
                  <CauseBlock
                    group={group}
                    locale={locale}
                    runHeadlines={runHeadlines}
                  />
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
