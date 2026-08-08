import type { ReactNode } from 'react';

import { timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { FilterBar } from '../filters';
import { panelLabels, rowLabels } from '../labels';
import { Panel } from '../panel';
import {
  dataOf,
  dependencyOf,
  list,
  number,
  readProjectedPanel,
  stateOf,
  text,
} from '../read';
import { RowList, type ListRow } from '../rows';
import { readViewState, type FilterName } from '../url-state';

/**
 * What am I responsible for, and what state is it in?
 *
 * Sorted worst-first by default, so the problems are at the top without anybody
 * filtering for them. `stale` and `absent` are their own states rather than
 * shades of `unhealthy`, because an integration outage and a broken machine
 * demand different responses — and a failed sweep must never make the estate look
 * like a disaster.
 *
 * **The state column is the state the deployment reports**, and the projected
 * inventory reports a lifecycle state today — `running`, `stopped` — rather than
 * a derived health verdict. The verdict is on the resource *detail*, as the
 * named checks it was derived from, which is the same panel the incident detail
 * shows. Deriving one here from those checks would be the console holding an
 * opinion about health, and the whole point of "health is derived, not declared"
 * is that exactly one thing derives it.
 *
 * Utilisation is a meter *and* a number where there is a capacity, and free text
 * where there is not. A bar alone is a shape somebody has to estimate, and "about
 * ninety per cent" is not a figure anybody acts on.
 */

export const RESOURCE_FILTERS: readonly FilterName[] = ['kind', 'state'];

/**
 * Worst first. The order is the triage order, not the alphabet.
 *
 * It names both vocabularies, because the field carries a lifecycle state today
 * and the derived verdict when the endpoint that computes one lands. A state
 * this console has not met sorts last and keeps its own word.
 */
const STATE_ORDER = [
  'unhealthy',
  'degraded',
  'stopped',
  'unknown',
  'stale',
  'absent',
  'healthy',
  'running',
];

function stateRank(record: unknown): number {
  const found = STATE_ORDER.indexOf(text(record, 'state'));
  return found === -1 ? STATE_ORDER.length : found;
}

/** The largest of the three readings a resource carries, as a percentage. */
function utilisation(record: unknown): number {
  return Math.max(
    number(record, 'volume_percent'),
    number(record, 'memory_percent'),
    number(record, 'cpu_percent'),
  );
}

export async function ResourcesScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, RESOURCE_FILTERS);

  const [resources, summary] = await Promise.all([
    readProjectedPanel('/v1/estate/resources', credential),
    readProjectedPanel('/v1/estate/summary', credential),
  ]);
  const records = list(dataOf(resources), 'resources');

  const kinds = [...new Set(records.map((record) => text(record, 'kind')))].sort();
  const states = [...new Set(records.map((record) => text(record, 'state')))].sort();

  const filtered = records.filter((record) => {
    const kind = state.filters.kind;
    const reported = state.filters.state;
    if (kind !== undefined && text(record, 'kind') !== kind) return false;
    if (reported !== undefined && text(record, 'state') !== reported) return false;
    return true;
  });

  const sorted = [...filtered].sort((left, right) => {
    if (state.sort !== '') {
      const order = text(left, state.sort).localeCompare(text(right, state.sort));
      return state.descending ? -order : order;
    }
    return stateRank(left) - stateRank(right);
  });

  const none = message(locale, 'surface.none');
  const rows: readonly ListRow[] = sorted.map((record) => {
    const id = text(record, 'resource_id');
    const used = utilisation(record);
    return {
      id,
      href: `/resources?selected=${id}`,
      cells: [
        { kind: 'text', text: text(record, 'name') },
        { kind: 'muted', text: text(record, 'kind') },
        {
          kind: 'muted',
          text: text(record, 'node') === '' ? none : text(record, 'node'),
        },
        { kind: 'status', text: text(record, 'state') },
        used > 0
          ? { kind: 'meter', text: text(record, 'name'), value: Math.round(used) }
          : { kind: 'muted', text: none },
        {
          kind: 'muted',
          text: timestamp(locale, text(record, 'last_seen_at'), now, zone).relative,
        },
      ],
    };
  });

  return (
    <>
      <AreaHeader
        area={areaFor('resources')}
        locale={locale}
        actions={
          <span className="text-meta text-muted">
            {message(locale, 'resources.summary', {
              watched: String(number(dataOf(summary), 'resources')),
              healthy: String(number(dataOf(summary), 'healthy')),
              degraded: String(number(dataOf(summary), 'degraded')),
            })}
          </span>
        }
      />

      <FilterBar
        path="/resources"
        state={state}
        filters={RESOURCE_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={[
          {
            name: 'kind',
            label: message(locale, 'resources.filter.kind'),
            options: kinds.map((value) => ({ value, label: value })),
          },
          {
            name: 'state',
            label: message(locale, 'resources.filter.state'),
            options: states.map((value) => ({ value, label: value })),
          },
        ]}
      />

      <Panel
        title={message(locale, 'resources.list.title')}
        state={stateOf(resources, rows.length === 0)}
        dependency={dependencyOf(resources)}
        labels={panelLabels(locale, message(locale, 'resources.list.title'))}
        empty={{
          heading: message(locale, 'resources.empty.heading'),
          body: message(locale, 'resources.empty.body'),
          actionLabel: message(locale, 'resources.empty.action'),
          href: '/configuration',
        }}
        action={
          <span className="text-meta text-muted">
            {state.sort === '' ? message(locale, 'resources.sorted') : ''}
          </span>
        }
      >
        <RowList
          path="/resources"
          state={state}
          filters={RESOURCE_FILTERS}
          labels={rowLabels(locale, message(locale, 'resources.list.caption'))}
          columns={[
            {
              key: 'name',
              header: message(locale, 'resources.column.name'),
              sortable: true,
            },
            {
              key: 'kind',
              header: message(locale, 'resources.column.kind'),
              sortable: true,
            },
            { key: 'node', header: message(locale, 'resources.column.parent') },
            {
              key: 'state',
              header: message(locale, 'resources.column.state'),
              sortable: true,
            },
            {
              key: 'utilisation',
              header: message(locale, 'resources.column.utilisation'),
            },
            {
              key: 'last_seen_at',
              header: message(locale, 'resources.column.lastSeen'),
            },
          ]}
          rows={rows}
        />
      </Panel>
    </>
  );
}
