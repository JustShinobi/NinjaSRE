import type { ReactNode } from 'react';

import { timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import type { SurfaceContext } from '../context';
import { extractionCause, firstCause, readSetupState, setupCause } from '../emptiness';
import { INVESTIGATION_STEP } from '../first-run/plan';
import { FilterBar, type FilterChoice } from '../filters';
import { panelLabels, rowLabels } from '../labels';
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
import { RowList, type ListRow } from '../rows';
import { readViewState, type FilterName } from '../url-state';

/**
 * The "Learned" tab of Knowledge: what past investigations left behind, and
 * what was learned from them.
 *
 * Episodes are browsable and each links to the run that produced it, which is
 * the property that makes the corpus evidence rather than assertion: a claim
 * about what happened in April is worth what the transcript behind it is worth.
 *
 * The component filter is passed to the *server* rather than applied here. The
 * search endpoint takes a component, and a console that read everything and
 * filtered it in a browser would be a console that stops working at the exact
 * size the corpus becomes worth having.
 *
 * A strategy is downstream of an episode, and an episode is downstream of an
 * investigation that finished. On a deployment where none has, saying so twice
 * — once for episodes, once for strategies — is two empty boxes past a
 * viewport for one fact. Below, the two collapse to the single section that
 * explains the whole chain, and the chain's own root cause: an unfinished
 * setup, named with a link to the place that finishes it.
 *
 * One of three tabs Knowledge asks about the same environment — learned,
 * documented, observed — so this content is rendered by
 * `screens/knowledge.tsx` beside `documents.tsx`'s and `topology.tsx`'s own.
 */

export const MEMORY_FILTERS: readonly FilterName[] = [
  // Carried through every filter link this tab regenerates, so choosing a
  // component or an outcome does not also silently switch Knowledge back to
  // its default tab. See `hrefFor`'s own docstring in `url-state.ts`.
  'tab',
  'component',
  'outcome',
];

export async function LearnedTab(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, MEMORY_FILTERS);
  const init = authorised(credential);
  const component = state.filters.component ?? '';

  const [episodes, setup] = await Promise.all([
    panelRead('/v1/memory/search', () =>
      read('/v1/memory/search', {
        ...init,
        ...(component === ''
          ? {}
          : { query: `?component=${encodeURIComponent(component)}` }),
      }),
    ),
    readSetupState(credential),
  ]);

  const records = list(dataOf(episodes), 'episodes');

  // Read only when there is an empty corpus to explain. On every other
  // rendering of this tab the answer changes nothing on the screen, and a
  // read whose result is discarded is a read the deployment served for
  // nobody.
  const finished =
    episodes.status === 'ready' && records.length === 0
      ? await finishedInvestigations(init)
      : 0;
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

  // A filter with nothing behind it but "Any" is not a filter, it is a
  // dropdown that teaches nothing. Both are computed from the whole corpus, not
  // the current selection, so choosing one value does not make the other vanish.
  const choices: readonly FilterChoice[] = [
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
  ].filter((choice) => choice.options.length > 0);

  // The corpus itself, not the current filter: choosing an outcome nothing
  // matches is a normal empty panel, not the deployment-wide story below.
  const corpusEmpty = episodes.status === 'ready' && records.length === 0;

  // Most specific first, and the extraction cause is the more specific of the
  // two: a deployment whose investigations have finished is past the setup
  // step this screen would otherwise blame, so "finish setting up" would be
  // advice for something already done.
  const cause = firstCause(
    extractionCause(locale, finished),
    setupCause(locale, setup, INVESTIGATION_STEP),
  );

  // The mechanism for both stays — an episode comes from an investigation that
  // ended, a strategy from episodes that agree — and, when the setup is why
  // neither has happened yet, one more sentence closes the chain with a link
  // to the place that finishes it.
  const cycleBody = [
    message(
      locale,
      // The mechanism keeps its "and none has been written yet" only when
      // nothing follows it. Where a cause does, that clause is the paragraph
      // asserting an absence and then immediately counting the runs behind
      // it — two sentences for one fact, in two different moods.
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

  return (
    <>
      {corpusEmpty || choices.length === 0 ? null : (
        <FilterBar
          path="/knowledge"
          state={state}
          filters={MEMORY_FILTERS}
          anyLabel={message(locale, 'surface.filter.any')}
          choices={choices}
        />
      )}

      {corpusEmpty ? (
        <Panel
          title={message(locale, 'memory.stats.title')}
          state={stateOf(episodes, true)}
          dependency={dependencyOf(episodes)}
          labels={panelLabels(locale, message(locale, 'memory.stats.title'))}
          empty={cycleEmpty}
        />
      ) : (
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
              path="/knowledge"
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
              href: '/knowledge?tab=learned',
            }}
          />
        </div>
      )}
    </>
  );
}

/**
 * How many investigations this deployment has actually concluded.
 *
 * Completed, not settled. A cancelled or failed run reached no conclusion for
 * an episode to be extracted from, so counting one would have the screen
 * blaming the corpus for a gap that was never going to be filled — the same
 * false causality `setupCause` exists to stop asserting, in a smaller place.
 *
 * A read that fails resolves to nought, which leaves the screen's own words
 * in place. That is the safe direction: a console that could not count the
 * runs must not start telling people their extraction is broken.
 */
async function finishedInvestigations(init: RequestInit): Promise<number> {
  const runs = await panelRead('/v1/runs', () => read('/v1/runs', init));
  if (runs.status !== 'ready') return 0;
  return list(dataOf(runs), 'runs').filter(
    (record) => text(record, 'status') === 'completed',
  ).length;
}
