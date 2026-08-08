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
  authorised,
  dataOf,
  dependencyOf,
  field,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { RowList, type ListRow } from '../rows';
import { readViewState, type FilterName } from '../url-state';

/**
 * The documents an investigation is allowed to read, and the changes one has
 * proposed to them.
 *
 * The proposal queue is a separate panel rather than a badge on a row, because
 * reviewing what an agent wants to write down is a different activity from
 * looking something up, and a queue nobody can see is a queue nobody works.
 */

export const KNOWLEDGE_FILTERS: readonly FilterName[] = ['kind'];

export async function KnowledgeScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, KNOWLEDGE_FILTERS);

  const documents = await panelRead('/v1/knowledge/documents', () =>
    read('/v1/knowledge/documents', authorised(credential)),
  );
  const records = list(dataOf(documents), 'documents');

  function kindOf(record: unknown): string {
    return text(field(record, 'metadata'), 'kind');
  }

  const kinds = [...new Set(records.map(kindOf))].filter((kind) => kind !== '').sort();
  const filtered = records.filter((record) => {
    const kind = state.filters.kind;
    return kind === undefined || kindOf(record) === kind;
  });

  const none = message(locale, 'surface.none');
  const rows: readonly ListRow[] = filtered.map((record) => ({
    id: text(record, 'document_id'),
    href: `/knowledge?selected=${text(record, 'document_id')}`,
    cells: [
      { kind: 'text', text: text(record, 'title') },
      { kind: 'muted', text: kindOf(record) === '' ? none : kindOf(record) },
      {
        kind: 'muted',
        text: timestamp(locale, text(record, 'updated_at'), now, zone).relative,
      },
    ],
  }));

  return (
    <>
      <AreaHeader area={areaFor('knowledge')} locale={locale} />

      <FilterBar
        path="/knowledge"
        state={state}
        filters={KNOWLEDGE_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={[
          {
            name: 'kind',
            label: message(locale, 'knowledge.column.kind'),
            options: kinds.map((value) => ({ value, label: value })),
          },
        ]}
      />

      <div className="flex flex-col gap-5">
        <Panel
          title={message(locale, 'knowledge.documents.title')}
          state={stateOf(documents, rows.length === 0)}
          dependency={dependencyOf(documents)}
          labels={panelLabels(locale, message(locale, 'knowledge.documents.title'))}
          empty={{
            heading: message(locale, 'knowledge.documents.empty.heading'),
            body: message(locale, 'knowledge.documents.empty.body'),
            actionLabel: message(locale, 'knowledge.documents.empty.action'),
            href: '/configuration',
          }}
        >
          <RowList
            path="/knowledge"
            state={state}
            filters={KNOWLEDGE_FILTERS}
            labels={rowLabels(locale, message(locale, 'knowledge.documents.caption'))}
            columns={[
              {
                key: 'title',
                header: message(locale, 'knowledge.column.title'),
                sortable: true,
              },
              { key: 'kind', header: message(locale, 'knowledge.column.kind') },
              {
                key: 'updated_at',
                header: message(locale, 'knowledge.column.updated'),
                sortable: true,
              },
            ]}
            rows={rows}
          />
        </Panel>

        <Panel
          title={message(locale, 'knowledge.proposals.title')}
          // Nothing serves agent-proposed changes yet. The panel says what one
          // is and where it would come from, which is the difference between a
          // queue that is empty and a queue nobody built.
          state={stateOf(documents, true)}
          dependency={dependencyOf(documents)}
          labels={panelLabels(locale, message(locale, 'knowledge.proposals.title'))}
          empty={{
            heading: message(locale, 'knowledge.proposals.empty.heading'),
            body: message(locale, 'knowledge.proposals.empty.body'),
            actionLabel: message(locale, 'knowledge.proposals.empty.action'),
            href: '/knowledge',
          }}
        />
      </div>
    </>
  );
}
