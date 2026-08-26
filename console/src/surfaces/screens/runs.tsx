import type { ReactNode } from 'react';

import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { FilterBar } from '../filters';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  list,
  number,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import {
  RunCard,
  namedEvidence,
  turnsFrom,
  type RunCardBody,
  type RunCardHead,
} from '../run-card';
import { evidenceOf } from '../run-evidence';
import { subjectOf } from '../run-subject';
import { triggerLabel } from '../run-trigger';
import { hrefFor, readViewState, withSelection, type FilterName } from '../url-state';

/**
 * Every run this deployment has recorded, and one of them open in place.
 *
 * The list was a table of six columns whose rows navigated away. Two things
 * were wrong with that and both are fixed here. A table's columns are the same
 * width for every row, so the column carrying what a run was *about* — the only
 * one anybody scans — was the one that got clipped; a card gives the subject
 * the line and demotes the identifier to the metadata it is. And a row that
 * navigates throws the list away, which is exactly what somebody comparing
 * several runs of one subject cannot afford.
 *
 * The open row is in the address, so it survives a reload, can be sent, and is
 * rendered on the server. Only the open run is read in full: the list read is
 * one request whatever the page holds, and the detail, the replay and the open
 * questions are three more for the one run somebody actually asked for.
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

export async function RunsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, RUN_FILTERS);
  const init = authorised(credential);

  const runs = await panelRead('/v1/runs', () => read('/v1/runs', init));
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

  // Newest first, always. A run list opened cold is a list somebody is looking
  // at because something just happened, and the sort control the table carried
  // sorted by fields — status, trigger — nobody ever wanted ordered by.
  const sorted = [...filtered].sort(
    (left, right) =>
      Date.parse(text(right, 'started_at')) - Date.parse(text(left, 'started_at')),
  );

  // The open run, if the address names one that is actually on this page. A
  // selection that survived a filter change names a run the reader can no
  // longer see, and reading it would render a body under no card.
  const openId =
    state.selection !== null &&
    sorted.some((record) => text(record, 'run_id') === state.selection)
      ? state.selection
      : null;

  const body = openId === null ? undefined : await openBody(openId, init);

  const cards = sorted.map((record) => {
    const id = text(record, 'run_id');
    const subject = subjectOf(record, locale);
    const open = id === openId;
    const head: RunCardHead = {
      runId: id,
      subject: subject.text,
      subjectFull: subject.full,
      status: text(record, 'status'),
      trigger: text(record, 'trigger'),
      startedAt: text(record, 'started_at'),
      seconds: durationOf(record),
      evidence: evidenceOf({
        evidence_assessed: field(record, 'evidence_assessed'),
        evidence_backed: field(record, 'evidence_backed'),
        evidence_missing: field(record, 'evidence_missing'),
      }),
    };
    return (
      <RunCard
        key={id}
        locale={locale}
        now={now}
        zone={zone}
        head={head}
        open={open}
        toggleHref={hrefFor(
          '/runs',
          withSelection(state, open ? null : id),
          RUN_FILTERS,
        )}
        {...(open && body !== undefined ? { body } : {})}
      />
    );
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
            options: triggers.map((trigger) => ({
              value: trigger,
              label: triggerLabel(locale, trigger),
            })),
          },
        ]}
      />

      <Panel
        title={message(locale, 'runs.list.title')}
        titleHidden
        bare
        state={stateOf(runs, cards.length === 0)}
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
      >
        <div className="flex flex-col gap-3">
          <p className="text-meta text-muted">
            {message(locale, 'surface.showing', {
              shown: String(cards.length),
              total: String(records.length),
            })}
          </p>
          {cards}
        </div>
      </Panel>
    </>
  );
}

/**
 * Everything the open card draws, read for that one run.
 *
 * Three reads rather than one, and each fails on its own: a replay the
 * deployment could not rebuild leaves the report and the questions on the
 * screen, which is a better card than an error where a card was.
 */
async function openBody(runId: string, init: RequestInit): Promise<RunCardBody> {
  const bound = { ...init, params: { run_id: runId } };
  const [detail, replay, interactions] = await Promise.all([
    panelRead('/v1/runs/{run_id}', () => read('/v1/runs/{run_id}', bound)),
    panelRead('/v1/runs/{run_id}/replay', () =>
      read('/v1/runs/{run_id}/replay', bound),
    ),
    panelRead('/v1/investigations/{run_id}/interactions', () =>
      read('/v1/investigations/{run_id}/interactions', bound),
    ),
  ]);

  const run = dataOf(detail);
  const replayed = dataOf(replay);
  const turns = turnsFrom(replayed);
  const assessment = namedEvidence(run);

  const waiting = list(dataOf(interactions), 'interactions')
    .filter((record) => field(record, 'is_open') !== false)
    .map((record) => text(record, 'question'))
    .filter((question) => question !== '');

  return {
    report: text(run, 'report').trim(),
    headline: text(run, 'headline').trim(),
    touchedResources: list(run, 'touched_resources').map(String),
    incidentId: text(run, 'incident_id'),
    tokens: number(replayed, 'total_tokens'),
    // Priced only when every turn carried a price. A total that silently
    // treated an unpriced turn as nothing would be a floor drawn as a total.
    priced: turns.length > 0 && number(replayed, 'unpriced_turns') === 0,
    turns,
    calls: turns.reduce((total, turn) => total + turn.calls.length, 0),
    events: turns.reduce((total, turn) => total + turn.calls.length * 2 + 1, 0),
    waiting,
    supporting: assessment.supporting,
    missing: assessment.missing,
  };
}
