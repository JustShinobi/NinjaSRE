import type { ReactNode } from 'react';

import NextLink from 'next/link';

import { SegmentedLinks } from '@/components';
import { timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import type { SurfaceContext } from '../context';
import { extractionCause, firstCause, readSetupState, setupCause } from '../emptiness';
import { INVESTIGATION_STEP } from '../first-run/plan';
import { panelLabels } from '../labels';
import { Panel, type PanelEmpty } from '../panel';
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
import { hrefFor, readViewState, withFilter, type FilterName } from '../url-state';
import { normaliseComponents, type ComponentType } from './component-normalisation';

/**
 * The "Learned" tab of Knowledge: what past investigations left behind, and
 * what was learned from them.
 *
 * Episodes are cards, each linking to the run that produced it — the
 * property that makes the corpus evidence rather than assertion. The
 * component filter groups by type and merges `container:<id>`/`guest:<id>`
 * into one option, because the staging audit that opened this feature found
 * the same guest listed twice under two prefixes. The side panel reads the
 * pending knowledge-typed proposals from the queue every proposal waits in —
 * never a second copy of that queue.
 *
 * One of three tabs Knowledge asks about the same environment — learned,
 * documented, observed — so this content is rendered by
 * `screens/knowledge.tsx` beside `documents.tsx`'s and `topology.tsx`'s own.
 */

export const MEMORY_FILTERS: readonly FilterName[] = ['tab', 'component', 'outcome'];

/** What the component filter's own label reads for each grouped type. */
const TYPE_LABEL: Readonly<Record<ComponentType, string>> = {
  service: 'memory.componentType.service',
  node: 'memory.componentType.node',
  guest: 'memory.componentType.guest',
  cluster: 'memory.componentType.cluster',
} as const;

/** The one proposal type this panel reads out of the shared queue. */
const KNOWLEDGE_PROPOSAL_TYPE = 'knowledge';

/** Where every proposal, knowledge included, is reviewed and decided. */
const PROPOSALS_HREF = '/decisions?tab=changes';

function outcomeShape(outcome: string): { readonly filled: boolean } {
  return { filled: outcome === 'resolved' };
}

function EpisodeCard({
  context,
  episode,
  activeComponent,
  state,
}: {
  readonly context: Pick<SurfaceContext, 'locale' | 'now' | 'zone'>;
  readonly episode: unknown;
  readonly activeComponent: string;
  readonly state: ReturnType<typeof readViewState>;
}): ReactNode {
  const { locale, now, zone } = context;
  const outcome = text(episode, 'outcome');
  const shape = outcomeShape(outcome);
  const runId = text(episode, 'run_id');
  const components = list(episode, 'components').map(String);
  return (
    <li
      data-testid="episode-card"
      data-outcome={outcome}
      className="flex flex-col gap-2 rounded-3 edge border-border bg-raised p-4"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`mt-1 icon-inline shrink-0 rounded-full ${shape.filled ? 'bg-success' : 'edge-ring border-warning bg-transparent'}`}
        />
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <span className="text-small font-medium">{text(episode, 'title')}</span>
          <span className="text-meta text-muted">{text(episode, 'summary')}</span>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap pl-6">
        {components.map((component) => (
          <a
            key={component}
            href={hrefFor(
              '/knowledge',
              withFilter(state, 'component', component),
              MEMORY_FILTERS,
            )}
            data-testid="episode-component-chip"
            data-active={component === activeComponent ? 'true' : 'false'}
            className={`rounded-full px-2 py-1 text-micro edge font-mono ${component === activeComponent ? 'bg-accent-bg text-accent border-accent' : 'text-muted'}`}
          >
            {component}
          </a>
        ))}
        <span
          data-testid="episode-time"
          className="ml-auto shrink-0 text-micro text-muted"
        >
          {timestamp(locale, text(episode, 'occurred_at'), now, zone).relative}
        </span>
        {runId === '' ? null : (
          <a
            href={`/runs/${runId}`}
            data-testid="episode-open-investigation"
            className="shrink-0 text-micro text-accent hover:underline"
          >
            {message(locale, 'memory.episode.openInvestigation')}
          </a>
        )}
      </div>
    </li>
  );
}

function ComponentFilter({
  locale,
  groups,
  active,
  path,
  state,
}: {
  readonly locale: SurfaceContext['locale'];
  readonly groups: ReturnType<typeof normaliseComponents>;
  readonly active: string;
  readonly path: string;
  readonly state: ReturnType<typeof readViewState>;
}): ReactNode {
  const activeLabel =
    active === ''
      ? message(locale, 'surface.filter.any')
      : (groups
          .flatMap((group) => group.options)
          .find((option) => option.canonical === active)?.display ?? active);
  return (
    <details data-testid="component-filter" className="relative">
      <summary
        data-testid="component-filter-toggle"
        className="flex items-center gap-2 rounded-2 edge border-border px-3 py-2 text-small cursor-pointer list-none"
      >
        {message(locale, 'memory.filter.component')} ·{' '}
        <span data-testid="component-filter-summary" className="text-accent">
          {activeLabel}
        </span>
      </summary>
      <div className="absolute z-10 mt-2 flex flex-col gap-3 rounded-3 edge border-border bg-raised p-3 shadow-1 max-w-prose">
        <a
          href={hrefFor(path, withFilter(state, 'component', ''), MEMORY_FILTERS)}
          className="text-micro text-muted hover:underline"
        >
          {message(locale, 'surface.filter.any')}
        </a>
        {groups.map((group) => (
          <div
            key={group.type}
            data-testid="component-filter-group"
            className="flex flex-col gap-1"
          >
            <span className="text-micro text-muted font-semibold uppercase tracking-wide">
              {message(locale, TYPE_LABEL[group.type] as Parameters<typeof message>[1])}{' '}
              <span
                data-testid="component-filter-group-count"
                className="font-mono normal-case"
              >
                {group.options.length}
              </span>
            </span>
            {group.options.map((option) => (
              <a
                key={option.canonical}
                href={hrefFor(
                  path,
                  withFilter(state, 'component', option.canonical),
                  MEMORY_FILTERS,
                )}
                data-testid="component-filter-option"
                className="text-small font-mono hover:underline"
              >
                {option.display}
              </a>
            ))}
          </div>
        ))}
      </div>
    </details>
  );
}

/** One component, queried against the search endpoint's own exact match. */
async function searchByComponent(
  component: string,
  init: RequestInit,
): Promise<unknown> {
  return read('/v1/memory/search', {
    ...init,
    query: `?component=${encodeURIComponent(component)}`,
  });
}

export async function LearnedTab(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, MEMORY_FILTERS);
  const init = authorised(credential);
  const component = state.filters.component ?? '';

  // The vocabulary the filter offers is read unfiltered, always: the search
  // endpoint's own `component` narrows the result set server-side, and a
  // vocabulary built from an already-narrowed page would lose every option
  // the current filter does not itself hold.
  const [vocabulary, proposals, documents, topology, setup] = await Promise.all([
    panelRead('/v1/memory/search', () => read('/v1/memory/search', init)),
    panelRead('/v1/proposals', () => read('/v1/proposals', init)),
    panelRead('/v1/knowledge/documents', () => read('/v1/knowledge/documents', init)),
    panelRead('/v1/topology/{node_id}', () =>
      read('/v1/topology/{node_id}', { ...init, params: { node_id: 'root' } }),
    ),
    readSetupState(credential),
  ]);

  const wholeCorpus = list(dataOf(vocabulary), 'episodes');
  const allComponents = [
    ...new Set(wholeCorpus.flatMap((record) => list(record, 'components').map(String))),
  ];
  const componentGroups = normaliseComponents(allComponents);

  // A merged option — `container:<id>` and `guest:<id>` folded into one —
  // still queries the server by exact match, once per raw spelling it
  // actually carries, and this is that resolution: never every episode
  // fetched and narrowed in the browser, always a bounded query per
  // observed spelling of the one thing that was clicked. A `component` the
  // vocabulary does not recognise (a stale deep link) is queried literally,
  // which is what makes "filter shown as active with an honest empty
  // result" possible instead of silently dropping it.
  const rawSpellings =
    component === ''
      ? []
      : (componentGroups
          .flatMap((group) => group.options)
          .find((option) => option.canonical === component)?.raw ?? [component]);

  const episodes =
    component === ''
      ? vocabulary
      : rawSpellings.length === 1
        ? await panelRead('/v1/memory/search', () =>
            searchByComponent(rawSpellings[0] ?? component, init),
          )
        : await panelRead('/v1/memory/search', async () => {
            const pages = await Promise.all(
              rawSpellings.map((spelling) => searchByComponent(spelling, init)),
            );
            const merged = new Map<string, unknown>();
            for (const page of pages) {
              for (const episode of list(page, 'episodes')) {
                merged.set(text(episode, 'episode_id'), episode);
              }
            }
            return { episodes: [...merged.values()] };
          });

  const records = list(dataOf(episodes), 'episodes');

  const finished =
    episodes.status === 'ready' && records.length === 0 && component === ''
      ? await finishedInvestigations(init)
      : 0;

  const outcomes = [
    ...new Set(wholeCorpus.map((record) => text(record, 'outcome')).filter(Boolean)),
  ].sort();

  const filtered = records.filter((record) => {
    const outcome = state.filters.outcome;
    return outcome === undefined || text(record, 'outcome') === outcome;
  });

  const corpusEmpty = episodes.status === 'ready' && records.length === 0;

  const cause = firstCause(
    extractionCause(locale, finished),
    setupCause(locale, setup, INVESTIGATION_STEP),
  );

  const cycleBody = [
    message(
      locale,
      cause === null ? 'memory.episodes.empty.body' : 'memory.episodes.empty.mechanism',
    ),
    message(locale, 'memory.strategies.empty.body'),
    ...(cause === null ? [] : [cause.body]),
  ].join(' ');

  const cycleEmpty: PanelEmpty = {
    heading: message(locale, 'memory.episodes.empty.heading'),
    body: cycleBody,
    actionLabel:
      cause === null
        ? message(locale, 'memory.episodes.empty.action')
        : cause.actionLabel,
    href: cause === null ? '/runs' : cause.href,
  };

  const pendingKnowledge =
    proposals.status === 'ready'
      ? list(dataOf(proposals), 'proposals').filter(
          (entry) => text(entry, 'proposal_type') === KNOWLEDGE_PROPOSAL_TYPE,
        )
      : [];

  const documentCount =
    documents.status === 'ready' ? list(dataOf(documents), 'documents').length : 0;
  const topologyBody = dataOf(topology);
  const topologyCount =
    topology.status === 'ready'
      ? new Set([
          ...list(topologyBody, 'dependencies').map((entry) => text(entry, 'node_id')),
          ...list(topologyBody, 'dependents').map((entry) => text(entry, 'node_id')),
        ]).size
      : 0;

  return (
    <>
      {corpusEmpty ? (
        <Panel
          title={message(locale, 'memory.stats.title')}
          state={stateOf(episodes, true)}
          dependency={dependencyOf(episodes)}
          labels={panelLabels(locale, message(locale, 'memory.stats.title'))}
          empty={cycleEmpty}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
          <div className="flex flex-col gap-3 min-w-0 lg:col-span-3">
            {outcomes.length === 0 ? null : (
              <div className="flex items-center gap-3 flex-wrap">
                <ComponentFilter
                  locale={locale}
                  groups={componentGroups}
                  active={component}
                  path="/knowledge"
                  state={state}
                />
                <SegmentedLinks
                  label={message(locale, 'memory.filter.outcome')}
                  selected={state.filters.outcome ?? ''}
                  options={[
                    {
                      id: '',
                      label: message(locale, 'surface.filter.any'),
                      href: hrefFor(
                        '/knowledge',
                        withFilter(state, 'outcome', ''),
                        MEMORY_FILTERS,
                      ),
                    },
                    ...outcomes.map((outcome) => ({
                      id: outcome,
                      label: outcome,
                      href: hrefFor(
                        '/knowledge',
                        withFilter(state, 'outcome', outcome),
                        MEMORY_FILTERS,
                      ),
                    })),
                  ]}
                />
                <span className="ml-auto text-micro text-muted">
                  {message(locale, 'memory.count', { count: filtered.length })}
                </span>
              </div>
            )}

            <Panel
              title={message(locale, 'memory.episodes.title')}
              titleHidden
              state={stateOf(episodes, filtered.length === 0)}
              dependency={dependencyOf(episodes)}
              labels={panelLabels(locale, message(locale, 'memory.episodes.title'))}
              empty={{
                heading: message(locale, 'memory.episodes.empty.heading'),
                body: message(locale, 'memory.episodes.empty.body'),
                actionLabel: message(locale, 'memory.episodes.empty.action'),
                href: '/runs',
              }}
            >
              <ul className="flex flex-col gap-3">
                {filtered.map((episode) => (
                  <EpisodeCard
                    key={text(episode, 'episode_id')}
                    context={{ locale, now, zone }}
                    episode={episode}
                    activeComponent={component}
                    state={state}
                  />
                ))}
              </ul>
            </Panel>
          </div>

          <div
            className="flex flex-col gap-3 min-w-0 lg:col-span-1"
            data-testid="knowledge-learned-panel"
          >
            <span className="text-strong text-small">
              {message(locale, 'memory.learned.title')}
            </span>
            {pendingKnowledge.length === 0 ? (
              <div
                data-testid="knowledge-proposal-empty"
                className="flex flex-col gap-2 rounded-3 edge border-border bg-raised p-3"
              >
                <p className="text-small text-muted">
                  {message(locale, 'memory.learned.empty')}
                </p>
                <a
                  href={PROPOSALS_HREF}
                  className="text-small text-accent hover:underline"
                >
                  {message(locale, 'nav.proposals')}
                </a>
              </div>
            ) : (
              pendingKnowledge.map((proposal) => (
                <div
                  key={text(proposal, 'proposal_id')}
                  data-testid="knowledge-proposal-card"
                  className="flex flex-col gap-2 rounded-3 edge border-border bg-raised p-3"
                >
                  <p className="text-small">{text(proposal, 'summary')}</p>
                  <span className="text-micro text-muted">
                    {message(locale, 'memory.learned.from', {
                      run: text(proposal, 'run_id') || text(proposal, 'correlation_id'),
                    })}
                  </span>
                  <a
                    href={PROPOSALS_HREF}
                    className="text-micro text-accent hover:underline"
                  >
                    {message(locale, 'memory.learned.promote')}
                  </a>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-5">
        <div
          data-testid="knowledge-preview-documents"
          className="flex items-center gap-3 rounded-3 edge border-border bg-raised p-3"
        >
          <p className="text-small">
            {message(
              locale,
              documentCount > 0
                ? 'memory.preview.documents'
                : 'memory.preview.documents.empty',
              { count: documentCount },
            )}
          </p>
          <NextLink
            href="/knowledge?tab=documents"
            prefetch={false}
            className="ml-auto shrink-0 text-small text-accent hover:underline"
          >
            {message(locale, 'memory.preview.open')}
          </NextLink>
        </div>
        <div
          data-testid="knowledge-preview-topology"
          className="flex items-center gap-3 rounded-3 edge border-border bg-raised p-3"
        >
          <p className="text-small">
            {message(
              locale,
              topologyCount > 0
                ? 'memory.preview.topology'
                : 'memory.preview.topology.empty',
              { count: topologyCount },
            )}
          </p>
          <NextLink
            href="/knowledge?tab=topology"
            prefetch={false}
            className="ml-auto shrink-0 text-small text-accent hover:underline"
          >
            {message(locale, 'memory.preview.open')}
          </NextLink>
        </div>
      </div>
    </>
  );
}

/**
 * How many investigations this deployment has actually concluded.
 *
 * A read that fails resolves to nought, which leaves the screen's own words
 * in place.
 */
async function finishedInvestigations(init: RequestInit): Promise<number> {
  const runs = await panelRead('/v1/runs', () => read('/v1/runs', init));
  if (runs.status !== 'ready') return 0;
  return list(dataOf(runs), 'runs').filter(
    (record) => text(record, 'status') === 'completed',
  ).length;
}
