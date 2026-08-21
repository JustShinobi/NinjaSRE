import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
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
import { readViewState, writeViewState, type FilterName } from '../url-state';

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
 */

export const AUDIT_FILTERS: readonly FilterName[] = ['actor', 'action'];

/** The permission the gateway requires to take the record away. */
const EXPORT = 'audit.export';

export async function AuditScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone, search } = context;
  const state = readViewState(search, AUDIT_FILTERS);

  const query = new URLSearchParams();
  for (const name of AUDIT_FILTERS) {
    const value = state.filters[name];
    if (value !== undefined) query.set(name, value);
  }
  const suffix = query.toString() === '' ? '' : `?${query.toString()}`;

  const events = await panelRead('/audit/events', () =>
    read('/audit/events', { ...authorised(credential), query: suffix }),
  );
  const records = list(dataOf(events), 'events');

  const actors = [...new Set(records.map((record) => text(record, 'actor_id')))].sort();
  const actions = [...new Set(records.map((record) => text(record, 'action')))].sort();

  const rows: readonly ListRow[] = records.map((record) => ({
    id: text(record, 'event_id'),
    href: `/audit?${writeViewState(
      { ...state, selection: text(record, 'event_id') },
      AUDIT_FILTERS,
    )}`,
    cells: [
      {
        kind: 'muted',
        text: timestamp(locale, text(record, 'occurred_at'), now, zone).relative,
      },
      { kind: 'identifier', text: text(record, 'actor_id') },
      { kind: 'text', text: text(record, 'action') },
      { kind: 'identifier', text: text(record, 'resource_id') },
      { kind: 'status', text: text(record, 'outcome') },
    ],
  }));

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

      <FilterBar
        path="/audit"
        state={state}
        filters={AUDIT_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={[
          {
            name: 'actor',
            label: message(locale, 'audit.filter.actor'),
            options: actors.map((value) => ({ value, label: value })),
          },
          {
            name: 'action',
            label: message(locale, 'audit.filter.action'),
            options: actions.map((value) => ({ value, label: value })),
          },
        ]}
      />

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
