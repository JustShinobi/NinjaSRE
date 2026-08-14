import type { ReactNode } from 'react';

import { TabLinks } from '@/components';
import { timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { emptyBecause, readSetupState, setupCause } from '../emptiness';
import { FilterBar, type FilterChoice } from '../filters';
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
  type PanelData,
} from '../read';
import { RowList, type ListRow } from '../rows';
import { readViewState, type FilterName } from '../url-state';
import { LearnedTab } from './memory';
import { TopologyTab } from './topology';

/**
 * The "Documents" tab of Knowledge: the documents an investigation is allowed
 * to read, and the changes one has proposed to them.
 *
 * **Nothing on this screen uploads, pastes, or connects a source.** There is
 * no such control anywhere in this console, so the empty state must not
 * promise one. A document reaches this corpus in one of two ways: an
 * administrator wires a sync job outside the console (a wiki, a shared
 * drive), or an investigation proposes something worth keeping and a human
 * approves that proposal — which is the one path this screen can actually
 * point at. Where the deployment's own setup is still unfinished, that is
 * named instead, because it is the more specific and more common reason a
 * first day's corpus is empty.
 *
 * **The proposal panel is a pointer, not a second list.** `/v1/proposals`
 * already carries knowledge-typed entries beside detector and configuration
 * ones — reviewing what an agent wants to write down happens in the one
 * queue every proposal waits in, now the "Changes proposed" tab of Decisions.
 * Rendering a second, silent copy of it here would be a queue that could
 * disagree with the one a reviewer actually decides on.
 *
 * One of three tabs Knowledge asks about the same environment — learned,
 * documented, observed — so `screens/knowledge.tsx` renders this beside
 * `memory.tsx`'s and `topology.tsx`'s own content.
 */

export const KNOWLEDGE_FILTERS: readonly FilterName[] = ['tab', 'kind'];

/** Where every proposal — knowledge included — is reviewed and decided. */
const PROPOSALS_HREF = '/decisions?tab=changes';

/**
 * The "Proposed by an agent" panel's own state.
 *
 * It reads nothing of its own — it is a description and a link, not a list —
 * so it is always ready. A constant rather than a fetch is what keeps that
 * true even if a future edit adds a read elsewhere on this screen.
 */
const PROPOSALS_POINTER: PanelData<undefined> = { status: 'ready', data: undefined };

export async function DocumentsTab(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, KNOWLEDGE_FILTERS);

  const [documents, setup] = await Promise.all([
    panelRead('/v1/knowledge/documents', () =>
      read('/v1/knowledge/documents', authorised(credential)),
    ),
    readSetupState(credential),
  ]);
  const cause = setupCause(locale, setup);
  const records = list(dataOf(documents), 'documents');

  function kindOf(record: unknown): string {
    return text(field(record, 'metadata'), 'kind');
  }

  const kinds = [...new Set(records.map(kindOf))].filter((kind) => kind !== '').sort();
  const filtered = records.filter((record) => {
    const kind = state.filters.kind;
    return kind === undefined || kindOf(record) === kind;
  });

  // A filter with nothing behind it but "Any" is not a filter, it is a
  // dropdown that teaches nothing. Computed from the whole corpus rather than
  // the current selection, and dropped from the bar entirely once it has
  // nothing behind it — the same rule the Memory screen's filters follow.
  const choices: readonly FilterChoice[] = [
    {
      name: 'kind',
      label: message(locale, 'knowledge.column.kind'),
      options: kinds.map((value) => ({ value, label: value })),
    },
  ].filter((choice) => choice.options.length > 0);

  const none = message(locale, 'surface.none');
  const rows: readonly ListRow[] = filtered.map((record) => ({
    id: text(record, 'document_id'),
    href: `/knowledge?tab=documents&selected=${text(record, 'document_id')}`,
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
      <FilterBar
        path="/knowledge"
        state={state}
        filters={KNOWLEDGE_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={choices}
      />

      <div className="flex flex-col gap-5">
        <Panel
          title={message(locale, 'knowledge.documents.title')}
          state={stateOf(documents, rows.length === 0)}
          dependency={dependencyOf(documents)}
          labels={panelLabels(locale, message(locale, 'knowledge.documents.title'))}
          empty={emptyBecause(
            {
              heading: message(locale, 'knowledge.documents.empty.heading'),
              body: message(locale, 'knowledge.documents.empty.body'),
              actionLabel: message(locale, 'knowledge.documents.empty.action'),
              // The one place this console can honestly send someone once setup
              // is finished: an investigation's own proposal, decided here.
              // There is no upload or connect-a-source control to link to —
              // "/configuration" named nothing about ingestion at all.
              href: PROPOSALS_HREF,
            },
            cause,
          )}
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
          // Not a second read of the proposal queue, and never "empty" on its
          // own behalf: `/v1/proposals` already carries knowledge-typed
          // entries beside every other kind, decided in the same place. This
          // panel names that and points there, rather than fetching and
          // rendering its own copy of a list that could drift from the one a
          // reviewer actually acts on.
          state={stateOf(PROPOSALS_POINTER, false)}
          dependency={dependencyOf(PROPOSALS_POINTER)}
          labels={panelLabels(locale, message(locale, 'knowledge.proposals.title'))}
          empty={{
            heading: message(locale, 'knowledge.proposals.empty.heading'),
            body: message(locale, 'knowledge.proposals.empty.body'),
            actionLabel: message(locale, 'nav.proposals'),
            href: PROPOSALS_HREF,
          }}
        >
          <p className="text-meta text-muted mb-3">
            {message(locale, 'knowledge.proposals.lead')}
          </p>
          <a
            href={PROPOSALS_HREF}
            data-testid="proposals-link"
            className="text-small text-accent underline underline-offset-2"
          >
            {message(locale, 'nav.proposals')}
          </a>
        </Panel>
      </div>
    </>
  );
}

/**
 * What the agent knows about this environment, in three tabs: episodes and
 * strategies it learned, documents it was taught, the graph it has observed.
 * All three used to be separate menu entries pointing at empty states that
 * explained one another; one screen with a shared empty-state vocabulary
 * says the same thing once.
 *
 * Documents stays the default tab — it is what `/knowledge` already showed
 * before this fusion, so a bookmark or an existing deep link still opens the
 * same content it always did.
 */
export const KNOWLEDGE_TABS = ['learned', 'documents', 'topology'] as const;

export type KnowledgeAreaTab = (typeof KNOWLEDGE_TABS)[number];

/** The tab the address names, and Documents when it names nothing known. */
export function tabFrom(value: string): KnowledgeAreaTab {
  return KNOWLEDGE_TABS.find((tab) => tab === value) ?? 'documents';
}

export async function KnowledgeScreen(context: SurfaceContext): Promise<ReactNode> {
  const { locale, search } = context;
  const tab = tabFrom(search.get('tab') ?? '');
  // Only the Topology tab carries a node in its own breadcrumb — see this
  // file's own note on why that decision moved up here rather than staying
  // inside `topology.tsx`.
  const node = tab === 'topology' ? (search.get('node') ?? '') : '';

  // Only the selected tab reads anything.
  const content =
    tab === 'learned'
      ? await LearnedTab(context)
      : tab === 'topology'
        ? await TopologyTab(context)
        : await DocumentsTab(context);

  return (
    <>
      <AreaHeader
        area={areaFor('knowledge')}
        locale={locale}
        nested={node === '' ? [] : [{ label: node }]}
      />

      <TabLinks
        label={message(locale, 'knowledge.tabs')}
        selected={tab}
        tabs={KNOWLEDGE_TABS.map((each) => ({
          id: each,
          label: message(locale, `knowledge.tab.${each}`),
          href: `?tab=${each}`,
        }))}
      />

      <div className="mt-4">{content}</div>
    </>
  );
}
