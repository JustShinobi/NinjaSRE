import type { ReactNode } from 'react';

import { formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
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
  number,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { RowList, type ListRow } from '../rows';
import { readViewState, type FilterName } from '../url-state';

/**
 * What past investigations left behind, and what was learned from them.
 *
 * Episodes are browsable and each links to the run that produced it, which is
 * the property that makes the corpus evidence rather than assertion: a claim
 * about what happened in April is worth what the transcript behind it is worth.
 *
 * The component filter is passed to the *server* rather than applied here. The
 * search endpoint takes a component, and a console that read everything and
 * filtered it in a browser would be a console that stops working at the exact
 * size the corpus becomes worth having.
 */

export const MEMORY_FILTERS: readonly FilterName[] = ['component', 'outcome'];

export async function MemoryScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, MEMORY_FILTERS);
  const init = authorised(credential);
  const component = state.filters.component ?? '';

  const [episodes, stats] = await Promise.all([
    panelRead('/v1/memory/search', () =>
      read('/v1/memory/search', {
        ...init,
        ...(component === ''
          ? {}
          : { query: `?component=${encodeURIComponent(component)}` }),
      }),
    ),
    panelRead('/v1/memory/stats', () => read('/v1/memory/stats', init)),
  ]);

  const records = list(dataOf(episodes), 'episodes');
  const components = [
    ...new Set(records.flatMap((record) => list(record, 'components').map(String))),
  ].sort();
  const outcomes = [
    ...new Set(records.map((record) => text(record, 'outcome'))),
  ].sort();

  const filtered = records.filter((record) => {
    const outcome = state.filters.outcome;
    return outcome === undefined || text(record, 'outcome') === outcome;
  });

  const rows: readonly ListRow[] = filtered.map((record) => ({
    id: text(record, 'episode_id'),
    // Every episode reaches the run that produced it. That link is the whole
    // difference between a corpus and a pile of assertions.
    href: `/runs/${text(record, 'run_id')}`,
    cells: [
      { kind: 'text', text: text(record, 'title') },
      { kind: 'status', text: text(record, 'outcome') },
      { kind: 'muted', text: list(record, 'components').map(String).join(', ') },
      {
        kind: 'muted',
        text: timestamp(locale, text(record, 'occurred_at'), now, zone).relative,
      },
    ],
  }));

  return (
    <>
      <AreaHeader
        area={areaFor('memory')}
        locale={locale}
        actions={
          <span className="text-meta text-muted">
            {message(locale, 'memory.stats.episodes')}:{' '}
            {formatNumber(locale, number(dataOf(stats), 'episode_count'))}
          </span>
        }
      />

      <FilterBar
        path="/memory"
        state={state}
        filters={MEMORY_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={[
          {
            name: 'component',
            label: message(locale, 'memory.filter.component'),
            options: components.map((value) => ({ value, label: value })),
          },
          {
            name: 'outcome',
            label: message(locale, 'memory.filter.outcome'),
            options: outcomes.map((value) => ({ value, label: value })),
          },
        ]}
      />

      <div className="flex flex-col gap-5">
        <Panel
          title={message(locale, 'memory.episodes.title')}
          state={stateOf(episodes, rows.length === 0)}
          dependency={dependencyOf(episodes)}
          labels={panelLabels(locale, message(locale, 'memory.episodes.title'))}
          empty={{
            heading: message(locale, 'memory.episodes.empty.heading'),
            body: message(locale, 'memory.episodes.empty.body'),
            actionLabel: message(locale, 'memory.episodes.empty.action'),
            href: '/runs',
          }}
        >
          <RowList
            path="/memory"
            state={state}
            filters={MEMORY_FILTERS}
            labels={rowLabels(locale, message(locale, 'memory.episodes.caption'))}
            columns={[
              {
                key: 'title',
                header: message(locale, 'memory.column.title'),
                sortable: true,
              },
              {
                key: 'outcome',
                header: message(locale, 'memory.column.outcome'),
                sortable: true,
              },
              {
                key: 'components',
                header: message(locale, 'memory.column.components'),
              },
              {
                key: 'occurred_at',
                header: message(locale, 'memory.column.occurred'),
                sortable: true,
              },
            ]}
            rows={rows}
          />
        </Panel>

        <Panel
          title={message(locale, 'memory.strategies.title')}
          // No endpoint serves synthesised strategies yet, and an empty panel
          // that said nothing would read as a corpus with nothing in it. This
          // says what a strategy is and what produces one.
          state={stateOf(episodes, true)}
          dependency={dependencyOf(episodes)}
          labels={panelLabels(locale, message(locale, 'memory.strategies.title'))}
          empty={{
            heading: message(locale, 'memory.strategies.empty.heading'),
            body: message(locale, 'memory.strategies.empty.body'),
            actionLabel: message(locale, 'memory.strategies.empty.action'),
            href: '/memory',
          }}
        />
      </div>
    </>
  );
}
