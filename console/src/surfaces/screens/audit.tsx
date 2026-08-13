import type { ReactNode } from 'react';

import { TabLinks } from '@/components';
import { Link } from '@/components/action';
import { formatCount, formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
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
import {
  hrefFor,
  readViewState,
  withFilter,
  writeViewState,
  type FilterName,
} from '../url-state';

/**
 * Who did what, when, and against which resource — filterable and exportable.
 *
 * The export is a link to the API's own export endpoint rather than something
 * assembled in a browser, for two reasons. A record the console reformatted is a
 * record whose provenance is the console, and an operator who has to keep their
 * own data does not want a CSV of the page they happened to be looking at.
 *
 * The filters are pushed to the server, because an audit log is the one
 * collection here that is genuinely unbounded.
 *
 * The one thing that arrives unbounded from the deployment itself is its own
 * polling: `default / credential.resolve / <integration> / ALLOWED`, written
 * every few seconds by the platform resolving a credential it already holds.
 * Two things below exist only because of that record, and both are load-bearing
 * rather than decorative:
 *
 * - **Bursts collapse.** A run of consecutive, identical events — same
 *   principal, action, resource and outcome — becomes one row carrying a count
 *   and the window it spans, so a burst does not cost the reader one scroll per
 *   event.
 * - **The system principal is excluded by default.** `default` is what the
 *   deployment calls itself; a human session carries its own principal. The
 *   reading a viewer lands on shows people, and a link — carrying how many
 *   events it is hiding — reaches the rest.
 *
 * Both apply to whatever was fetched, not to the whole table: the gateway has
 * no "not this principal" query, so the exclusion above happens here, against a
 * page pulled well past the ordinary default specifically so a human action
 * does not fall out of the window before this screen ever sees it.
 */

export const AUDIT_FILTERS: readonly FilterName[] = [
  'actor',
  'action',
  'audience',
  'since',
];

/** The permission the gateway requires to take the record away. */
const EXPORT = 'audit.export';

/** What the deployment calls itself. Every other principal is somebody's session. */
const SYSTEM_PRINCIPAL = 'default';

/** How many events a page pulls, well past the gateway's own default of 100.
 *
 * The audience exclusion below is client-side — there is no "not this
 * principal" query — so a human action has to still be *in* what was fetched
 * for that exclusion to find it, and a hundred rows of polling can be minutes.
 */
const EVENT_LIMIT = 500;

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
 * `credential.resolve` and `ALLOWED` are exact and machine-shaped, which is
 * exactly what makes them unreadable to somebody who does not carry the
 * internal glossary. This does not invent meaning the record does not carry —
 * it only stops asking the reader to parse punctuation and casing.
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

export async function AuditScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone, search } = context;
  const state = readViewState(search, AUDIT_FILTERS);
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
    href: `/audit?${writeViewState(
      { ...state, selection: group.eventId },
      AUDIT_FILTERS,
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
      { kind: 'status', text: humanize(group.outcome) },
    ],
  }));

  // A choice with nothing beside "Any" narrows nothing — every record already
  // carries the one value it has — so it is left out rather than shown as a
  // control with nothing to control.
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
  ].filter((choice) => choice.options.length > 1);

  const nowIso = now.toISOString();
  const periods = PERIOD_PRESET_DAYS.map((days) => {
    const since = new Date(now.getTime() - days * DAY_MS).toISOString();
    return {
      id: `days-${String(days)}`,
      since,
      href: hrefFor('/audit', withFilter(state, 'since', since), AUDIT_FILTERS),
      label: message(locale, 'run.changes.window', {
        start: timestamp(locale, since, now, zone).absolute,
        end: timestamp(locale, nowIso, now, zone).absolute,
      }),
    };
  });
  const currentSince = state.filters.since;
  const selectedPeriod =
    currentSince === undefined
      ? 'any'
      : (periods.find((preset) => preset.since === currentSince)?.id ?? '');

  return (
    <>
      <AreaHeader
        area={areaFor('audit')}
        locale={locale}
        actions={
          // Absent, not disabled, for a viewer who may not export.
          may(viewer, EXPORT) ? (
            <Link href={`/audit/export${suffix}`} data-testid="audit-export">
              {message(locale, 'surface.export')}
            </Link>
          ) : undefined
        }
      />

      {choices.length === 0 ? null : (
        <FilterBar
          path="/audit"
          state={state}
          filters={AUDIT_FILTERS}
          anyLabel={message(locale, 'surface.filter.any')}
          choices={choices}
        />
      )}

      <TabLinks
        tabs={[
          {
            id: 'any',
            label: message(locale, 'surface.filter.any'),
            href: hrefFor('/audit', withFilter(state, 'since', ''), AUDIT_FILTERS),
          },
          ...periods,
        ]}
        selected={selectedPeriod}
        label={message(locale, 'audit.column.occurred')}
      />

      {systemRecords.length > 0 && explicitActor === undefined ? (
        <p className="text-meta text-muted my-3">
          <a
            href={hrefFor(
              '/audit',
              withFilter(state, 'audience', audience === 'all' ? '' : 'all'),
              AUDIT_FILTERS,
            )}
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
        state={stateOf(events, rows.length === 0)}
        dependency={dependencyOf(events)}
        labels={panelLabels(locale, message(locale, 'audit.title'))}
        empty={{
          heading: message(locale, 'audit.empty.heading'),
          body: message(locale, 'audit.empty.body'),
          actionLabel: message(locale, 'audit.empty.action'),
          href: '/audit',
        }}
      >
        {events.status === 'ready' && total > records.length ? (
          <p className="text-meta text-muted mb-3" data-testid="audit-truncated">
            {message(locale, 'surface.showing', {
              shown: formatNumber(locale, records.length),
              total: formatNumber(locale, total),
            })}
          </p>
        ) : null}
        <RowList
          path="/audit"
          state={state}
          filters={AUDIT_FILTERS}
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
