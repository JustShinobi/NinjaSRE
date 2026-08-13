import type { ReactNode } from 'react';

import { formatDuration, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { readFailure } from '../failures';
import { FilterBar } from '../filters';
import { panelLabels, rowLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { RowList, type ListRow } from '../rows';
import { readViewState, type FilterName } from '../url-state';

/**
 * Every run this deployment has recorded, filterable, sortable and shareable.
 *
 * The filters are in the address rather than in component state, the sort is a
 * link rather than a click handler, and the list is windowed — so ten thousand
 * runs cost what ten do, and the view somebody is looking at is a view they can
 * send.
 */

/** The filters this screen declares, in the order the address writes them. */
export const RUN_FILTERS: readonly FilterName[] = ['status', 'trigger'];

/** How long a run took, in seconds, or nought while it is still going. */
function durationOf(record: unknown): number {
  const started = Date.parse(text(record, 'started_at'));
  const finished = Date.parse(text(record, 'finished_at'));
  if (Number.isNaN(started) || Number.isNaN(finished)) return 0;
  return Math.max(0, (finished - started) / 1000);
}

/** `value`, or the sentence that says nothing was recorded. */
function orNone(value: string, none: string): string {
  return value === '' ? none : value;
}

export async function RunsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, RUN_FILTERS);

  const runs = await panelRead('/v1/runs', () =>
    read('/v1/runs', authorised(credential)),
  );
  const records = list(dataOf(runs), 'runs');

  const statuses = [...new Set(records.map((record) => text(record, 'status')))].sort();
  const triggers = [
    ...new Set(records.map((record) => text(record, 'trigger'))),
  ].sort();

  const filtered = records.filter((record) =>
    Object.entries(state.filters).every(
      ([name, value]) => text(record, name) === value,
    ),
  );

  const sorted = [...filtered].sort((left, right) => {
    const column = state.sort === '' ? 'started_at' : state.sort;
    const order =
      column === 'duration'
        ? durationOf(left) - durationOf(right)
        : text(left, column).localeCompare(text(right, column));
    // Newest first by default: a run list opened cold is a list somebody is
    // looking at because something just happened.
    return state.sort === '' ? -order : state.descending ? -order : order;
  });

  const none = message(locale, 'surface.none');
  const rows: readonly ListRow[] = sorted.map((record) => {
    const id = text(record, 'run_id');
    const seconds = durationOf(record);
    return {
      id,
      href: `/runs/${id}`,
      cells: [
        { kind: 'identifier', text: id },
        { kind: 'status', text: text(record, 'status') },
        { kind: 'text', text: text(record, 'trigger') },
        // The subject column, not a place for a stack trace. A run that failed
        // because nothing is configured used to fill this cell with the
        // deployment's own exception, repeated on every row it happened to.
        // The deployment's words are still on the run itself.
        {
          kind: 'muted',
          text: orNone(readFailure(text(record, 'summary'), locale).title, none),
        },
        {
          kind: 'muted',
          text: timestamp(locale, text(record, 'started_at'), now, zone).relative,
        },
        {
          kind: 'numeric',
          text: seconds === 0 ? none : formatDuration(locale, seconds),
        },
      ],
    };
  });

  const filtering = Object.keys(state.filters).length > 0;

  return (
    <>
      <AreaHeader area={areaFor('runs')} locale={locale} />

      <FilterBar
        path="/runs"
        state={state}
        filters={RUN_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={[
          {
            name: 'status',
            label: message(locale, 'runs.filter.status'),
            options: statuses.map((status) => ({ value: status, label: status })),
          },
          {
            name: 'trigger',
            label: message(locale, 'runs.filter.trigger'),
            options: triggers.map((trigger) => ({ value: trigger, label: trigger })),
          },
        ]}
      />

      <Panel
        title={message(locale, 'runs.list.title')}
        state={stateOf(runs, rows.length === 0)}
        dependency={dependencyOf(runs)}
        labels={panelLabels(locale, message(locale, 'runs.list.title'))}
        empty={
          filtering
            ? {
                heading: message(locale, 'runs.filtered.heading'),
                body: message(locale, 'runs.filtered.body'),
                actionLabel: message(locale, 'runs.filtered.action'),
                href: '/runs',
              }
            : {
                heading: message(locale, 'runs.empty.heading'),
                body: message(locale, 'runs.empty.body'),
                actionLabel: message(locale, 'runs.empty.action'),
                href: '/',
              }
        }
        action={
          <span className="text-meta text-muted">
            {message(locale, 'surface.showing', {
              shown: String(rows.length),
              total: String(records.length),
            })}
          </span>
        }
      >
        <RowList
          path="/runs"
          state={state}
          filters={RUN_FILTERS}
          labels={rowLabels(locale, message(locale, 'runs.list.caption'))}
          columns={[
            {
              key: 'run_id',
              header: message(locale, 'runs.column.run'),
              sortable: true,
            },
            {
              key: 'status',
              header: message(locale, 'runs.column.status'),
              sortable: true,
            },
            {
              key: 'trigger',
              header: message(locale, 'runs.column.trigger'),
              sortable: true,
            },
            { key: 'summary', header: message(locale, 'runs.column.subject') },
            {
              key: 'started_at',
              header: message(locale, 'runs.column.started'),
              sortable: true,
            },
            {
              key: 'duration',
              header: message(locale, 'runs.column.duration'),
              numeric: true,
              sortable: true,
            },
          ]}
          rows={rows}
        />
      </Panel>
    </>
  );
}
