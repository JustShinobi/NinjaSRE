import type { ReactNode } from 'react';

import { TabLinks } from '@/components';
import { Link } from '@/components/action';
import { formatCount, formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { FilterBar, type FilterChoice } from '../filters';
import { panelLabels, rowLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  list,
  number,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { RowList, type ListRow } from '../rows';
import { hrefFor, readViewState, withFilter, type FilterName } from '../url-state';

/**
 * Audit log, on its own address.
 *
 * The Settings page that replaces the Administration screen's old "Audit"
 * tab, and the two reasons it exists as its own module rather than a thin
 * wrapper around that tab.
 *
 * **Every link here addresses this page.** The tab this absorbs built every
 * navigational control — the period presets, the "Any" link, a row's own
 * href, the audience toggle, the empty state's action — from a path literal
 * naming `/administration`. That was harmless while this content only ever
 * rendered there; it stopped being harmless the day this same function began
 * rendering at `/settings/audit-log` too, an address whose own query carries
 * no `tab`. A period preset built that way still pointed at
 * `/administration?since=…`, and the retired route's own redirect table reads
 * a request with no `tab` as the *default* tab — Members & roles — so
 * clicking "the next 30 days" from this page ejected the operator onto a
 * different one. Building every link from this module's own path removes the
 * hazard rather than papering over one call site of it.
 *
 * **Every count on this page describes the population it actually draws, not
 * the population it fetched.** The system principal's own polling is excluded
 * from the reading a viewer lands on by default (see below), and that
 * exclusion happens after the fetch — so a window whose only activity was
 * that polling has fetched something and drawn nothing. The panel's own empty
 * state is decided by what survived the exclusion, exactly like the
 * truncation notice above it: both used to be computed from the raw fetch,
 * which is how a screen ended up stating "Showing 200 of 156,735" over a
 * table with zero rows in it. The audience toggle is what makes the resulting
 * empty state honest rather than mute — it says how many events are hidden
 * and offers to show them — and it renders outside the panel, so it is never
 * itself hidden by the panel's own empty state.
 */

const PATH = '/settings/audit-log';
const ID = 'settings-audit-log';

export const AUDIT_LOG_FILTERS: readonly FilterName[] = [
  'actor',
  'action',
  'audience',
  'since',
];

/** The permission the gateway requires to take the record away. */
const EXPORT = 'audit.export';

/** What the deployment calls itself. Every other principal is somebody's session. */
const SYSTEM_PRINCIPAL = 'default';

/**
 * How many events a page pulls, well past the gateway's own default of 100.
 *
 * The audience exclusion below is client-side — there is no "not this
 * principal" query — so a human action has to still be *in* what was fetched
 * for that exclusion to find it, and a hundred rows of polling can be
 * minutes.
 *
 * Capped at the gateway's own page bound (`MAX_QUERY_PAGE_SIZE`,
 * `config/constants/persistence.py`, currently 200) rather than past it: the
 * repository raises on anything larger instead of quietly shortening the
 * page, so asking for more than this turns every load of this screen into a
 * failed one rather than a merely narrower one.
 */
const EVENT_LIMIT = 200;

/** This screen's filter names, mapped to what the gateway's query calls them. */
const API_PARAM: Readonly<Record<string, string>> = {
  actor: 'actor_id',
  action: 'action',
  since: 'since',
};

const DAY_MS = 24 * 60 * 60 * 1000;

/** How far back each period preset reaches. */
const PERIOD_PRESET_DAYS: readonly number[] = [7, 30];

/**
 * `value`, with its separators opened into spaces and each word capitalised.
 *
 * `credential.resolve` is exact and machine-shaped, which is exactly what
 * makes it unreadable to somebody who does not carry the internal glossary.
 * This does not invent meaning the record does not carry — it only stops
 * asking the reader to parse punctuation and casing.
 */
function humanize(value: string): string {
  const words = value.split(/[._-]+/).filter((word) => word.length > 0);
  if (words.length === 0) return value;
  return words
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/** One row after a burst has been collapsed into it — a burst of one is itself. */
interface AuditGroup {
  readonly eventId: string;
  readonly actorId: string;
  readonly action: string;
  readonly resourceId: string;
  readonly outcome: string;
  /** The most recent event's instant — the gateway returns newest first. */
  readonly latest: string;
  readonly earliest: string;
  readonly count: number;
}

/**
 * `records`, with a run of consecutive, identical events collapsed into one.
 *
 * "Identical" is the four fields a reader would use to tell two rows apart at
 * a glance — who, what, on which resource, and what happened — deliberately
 * not the instant, which is exactly the field that varies inside a burst.
 * Consecutive rather than "anywhere on the page", so two unrelated
 * resolutions that happen to match do not merge just because nothing
 * different landed between them in this fetch.
 */
function groupBursts(records: readonly unknown[]): readonly AuditGroup[] {
  const groups: AuditGroup[] = [];
  for (const record of records) {
    const actorId = text(record, 'actor_id');
    const action = text(record, 'action');
    const resourceId = text(record, 'resource_id');
    const outcome = text(record, 'outcome');
    const occurredAt = text(record, 'occurred_at');
    const last = groups[groups.length - 1];
    if (
      last?.actorId === actorId &&
      last.action === action &&
      last.resourceId === resourceId &&
      last.outcome === outcome
    ) {
      groups[groups.length - 1] = {
        ...last,
        earliest: occurredAt,
        count: last.count + 1,
      };
      continue;
    }
    groups.push({
      eventId: text(record, 'event_id'),
      actorId,
      action,
      resourceId,
      outcome,
      latest: occurredAt,
      earliest: occurredAt,
      count: 1,
    });
  }
  return groups;
}

/** The page's own body: filters, presets, the list, and the export. */
async function content(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone, search } = context;
  const state = readViewState(search, AUDIT_LOG_FILTERS);
  const explicitActor = state.filters.actor;

  const query = new URLSearchParams();
  for (const [name, param] of Object.entries(API_PARAM)) {
    const value = state.filters[name];
    if (value !== undefined) query.set(param, value);
  }
  query.set('limit', String(EVENT_LIMIT));
  const suffix = `?${query.toString()}`;

  const events = await panelRead('/audit/events', () =>
    read('/audit/events', { ...authorised(credential), query: suffix }),
  );
  const records = list(dataOf(events), 'events');
  const total = number(dataOf(events), 'total');

  const actors = [...new Set(records.map((record) => text(record, 'actor_id')))].sort();
  const actions = [...new Set(records.map((record) => text(record, 'action')))].sort();

  const systemRecords = records.filter(
    (record) => text(record, 'actor_id') === SYSTEM_PRINCIPAL,
  );
  const audience = state.filters.audience ?? '';
  // The default reading: people, not the deployment's own polling. An
  // explicit principal already says exactly who to show, so the exclusion
  // below only applies when nobody asked for one in particular.
  const visible =
    explicitActor !== undefined || audience === 'all'
      ? records
      : records.filter((record) => text(record, 'actor_id') !== SYSTEM_PRINCIPAL);

  const groups = groupBursts(visible);

  const rows: readonly ListRow[] = groups.map((group) => ({
    id: group.eventId,
    href: `${PATH}${hrefFor(
      '',
      { ...state, selection: group.eventId },
      AUDIT_LOG_FILTERS,
    )}`,
    cells: [
      {
        kind: 'muted',
        text:
          group.count > 1
            ? `${formatCount(locale, group.count, 'transcript.events.one', 'transcript.events')} — ${message(
                locale,
                'run.changes.window',
                {
                  start: timestamp(locale, group.earliest, now, zone).absolute,
                  end: timestamp(locale, group.latest, now, zone).absolute,
                },
              )}`
            : timestamp(locale, group.latest, now, zone).relative,
      },
      { kind: 'identifier', text: group.actorId },
      { kind: 'text', text: humanize(group.action) },
      { kind: 'identifier', text: group.resourceId },
      // Raw, like every other screen's status cell — `Badge` already renders
      // it in upper case, and a humanised label here would not match any of
      // the design system's own declared, lower-case status words, so it
      // would silently draw as an unrecognised, neutral chip instead of the
      // role this outcome actually has.
      { kind: 'status', text: group.outcome },
    ],
  }));

  const choices: readonly FilterChoice[] = [
    {
      name: 'actor',
      label: message(locale, 'audit.filter.actor'),
      options: actors.map((value) => ({ value, label: value })),
    },
    {
      name: 'action',
      label: message(locale, 'audit.filter.action'),
      options: actions.map((value) => ({ value, label: humanize(value) })),
    },
    // A choice with nothing beside "Any" narrows nothing — every record
    // already carries the one value it has — so it is left out rather than
    // shown as a control with nothing to control.
  ].filter((choice) => choice.options.length > 1);

  const periods = PERIOD_PRESET_DAYS.map((days) => {
    const since = new Date(now.getTime() - days * DAY_MS).toISOString();
    return {
      id: `days-${String(days)}`,
      since,
      href: `${PATH}${hrefFor('', withFilter(state, 'since', since), AUDIT_LOG_FILTERS)}`,
      label: message(locale, 'settings.auditLog.period.days', { days: String(days) }),
    };
  });
  const currentSince = state.filters.since;
  // Matched by how many whole days back `currentSince` lands from the
  // request's own clock, not by exact millisecond equality against a
  // preset's own `since` — a preset's link is built from an instant that
  // keeps moving with the wall clock, so a URL clicked even a second after
  // the page that offered it was rendered carries a `since` no later render
  // can ever equal exactly. Rounding is what makes yesterday's link for "the
  // last 7 days" still read as the last 7 days today.
  const impliedDays =
    currentSince === undefined
      ? undefined
      : Math.round((now.getTime() - Date.parse(currentSince)) / DAY_MS);
  const selectedPeriod =
    currentSince === undefined
      ? 'any'
      : impliedDays !== undefined && PERIOD_PRESET_DAYS.includes(impliedDays)
        ? `days-${String(impliedDays)}`
        : '';

  return (
    <>
      {/* Absent, not disabled, for a viewer who may not export. Inline rather
          than in the page header: an export control that only means
          something on this one panel does not belong beside the page's own
          title. */}
      {may(viewer, EXPORT) ? (
        <p className="flex justify-end mb-3">
          <Link href={`/audit/export${suffix}`} data-testid="audit-export">
            {message(locale, 'surface.export')}
          </Link>
        </p>
      ) : null}

      {choices.length === 0 ? null : (
        <FilterBar
          path={PATH}
          state={state}
          filters={AUDIT_LOG_FILTERS}
          anyLabel={message(locale, 'surface.filter.any')}
          choices={choices}
        />
      )}

      <TabLinks
        tabs={[
          {
            id: 'any',
            label: message(locale, 'surface.filter.any'),
            href: `${PATH}${hrefFor('', withFilter(state, 'since', ''), AUDIT_LOG_FILTERS)}`,
          },
          ...periods,
        ]}
        selected={selectedPeriod}
        label={message(locale, 'settings.auditLog.period.label')}
      />

      {systemRecords.length > 0 && explicitActor === undefined ? (
        <p className="text-meta text-muted my-3">
          <a
            href={`${PATH}${hrefFor(
              '',
              withFilter(state, 'audience', audience === 'all' ? '' : 'all'),
              AUDIT_LOG_FILTERS,
            )}`}
            data-testid="audit-audience-toggle"
            aria-current={audience === 'all' ? 'true' : undefined}
            className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
          >
            {SYSTEM_PRINCIPAL}
            {' — '}
            {formatCount(
              locale,
              systemRecords.length,
              'transcript.events.one',
              'transcript.events',
            )}
          </a>
        </p>
      ) : null}

      <Panel
        title={message(locale, 'audit.title')}
        // Decided by what the page actually draws — the rows below, after
        // the audience exclusion — never by what was merely fetched. A
        // window whose whole fetch is the deployment's own polling now draws
        // nothing and says so, honestly, with the toggle above already
        // saying why and offering the way out.
        state={stateOf(events, rows.length === 0)}
        dependency={dependencyOf(events)}
        labels={panelLabels(locale, message(locale, 'audit.title'))}
        empty={{
          heading: message(locale, 'audit.empty.heading'),
          body: message(locale, 'audit.empty.body'),
          actionLabel: message(locale, 'audit.empty.action'),
          href: `${PATH}${hrefFor('', withFilter(state, 'since', ''), AUDIT_LOG_FILTERS)}`,
        }}
      >
        {events.status === 'ready' && total > visible.length ? (
          <p className="text-meta text-muted mb-3" data-testid="audit-truncated">
            {message(locale, 'surface.showing', {
              // The population this page actually draws — every event
              // visible.length accounts for is represented in the rows
              // below, individually or folded into a burst's own count —
              // never `records.length`, which can count events the audience
              // exclusion above already took back out.
              shown: formatNumber(locale, visible.length),
              total: formatNumber(locale, total),
            })}
          </p>
        ) : null}
        <RowList
          path={PATH}
          state={state}
          filters={AUDIT_LOG_FILTERS}
          labels={rowLabels(locale, message(locale, 'audit.caption'))}
          columns={[
            {
              key: 'occurred_at',
              header: message(locale, 'audit.column.occurred'),
              sortable: true,
            },
            { key: 'actor_id', header: message(locale, 'audit.column.actor') },
            {
              key: 'action',
              header: message(locale, 'audit.column.action'),
              sortable: true,
            },
            { key: 'resource_id', header: message(locale, 'audit.column.subject') },
            { key: 'outcome', header: message(locale, 'audit.column.outcome') },
          ]}
          rows={rows}
        />
      </Panel>
    </>
  );
}

/**
 * The whole `/settings/audit-log` page: the Settings header, then this
 * screen's own body.
 *
 * Exported separately from `content` so a future page that only wants the
 * body — a drill-down, a print view — is not stuck re-deriving the header.
 */
export async function AuditLogScreen(context: SurfaceContext): Promise<ReactNode> {
  return (
    <>
      <SettingsPageHeader page={settingsPageFor(ID)} locale={context.locale} />
      {await content(context)}
    </>
  );
}
