import type { ReactNode } from 'react';
import NextLink from 'next/link';

import { Link, SegmentedLinks, type SegmentedOption } from '@/components';
import { Badge } from '@/components/status';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import {
  emptyBecause,
  firstCause,
  readSetupState,
  setupCause,
  watchingCause,
} from '../emptiness';
import { INVESTIGATION_STEP } from '../first-run/plan';
import { panelLabels, rowLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  flag,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { RowList, type ListRow } from '../rows';
import { hrefFor, readViewState, withFilter, type FilterName } from '../url-state';
import { IncidentGroupList } from '../incident-group-list';
import { groupBySubject } from '../incident-groups';
import { degradedFindingsWithoutDetector } from './detector-coverage-gap';
import { subjectOf } from '../run-subject';

/**
 * What a detector opened, and what happened to it since.
 *
 * Grouped by state and ordered by severity then age, which is the order somebody
 * triages in. The filters are in the address like every other list here, so a
 * link to "everything critical and open" is a link.
 */

export const INCIDENT_FILTERS: readonly FilterName[] = ['state', 'severity'];

/** The parameter carrying how the listing is shaped rather than what it holds. */
export const VIEW_PARAM = 'view';

/** Every firing on its own row, rather than folded under its cause. */
export const FLAT_VIEW = 'flat';

/**
 * What the address carries: the filters, and the view.
 *
 * The view rides with the filters so that sorting or filtering does not throw
 * it away — `writeViewState` rebuilds the query from the declared list and
 * nothing else, so a parameter that is not declared is a parameter every link
 * on the screen silently drops. It is deliberately *not* in
 * `INCIDENT_FILTERS`: that list is also what narrows the records, and an
 * incident has no `view` field to match against.
 */
export const INCIDENT_ADDRESS: readonly FilterName[] = [
  ...INCIDENT_FILTERS,
  VIEW_PARAM,
];

/** Most severe first. A list sorted alphabetically by severity is a list nobody reads. */
const SEVERITY_ORDER = ['critical', 'high', 'warning', 'medium', 'low', 'info'];

/** The one severity this screen's own segmented control names outright. */
const CRITICAL_SEVERITY = 'critical';

function severityRank(record: unknown): number {
  const found = SEVERITY_ORDER.indexOf(text(record, 'severity'));
  return found === -1 ? SEVERITY_ORDER.length : found;
}

function IncidentPreview({ locale }: Pick<SurfaceContext, 'locale'>): ReactNode {
  return (
    <section
      id="incident-preview"
      data-testid="incident-preview"
      aria-labelledby="incident-preview-title"
      className="mt-5 flex flex-col gap-3 rounded-3 edge border-border bg-raised p-4 shadow-1"
    >
      <div className="flex flex-col gap-1">
        <h3 id="incident-preview-title" className="text-strong">
          {message(locale, 'incidents.preview.title')}
        </h3>
        <p className="text-small text-muted">
          {message(locale, 'incidents.preview.body')}
        </p>
      </div>
      <p className="text-small text-strong">
        {message(locale, 'incidents.preview.example.title')}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Badge status="critical" />
        <Badge status="open" />
      </div>
      <dl className="flex flex-col gap-2 text-small">
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          <dt className="text-muted">
            {message(locale, 'incidents.preview.label.detector')}
          </dt>
          <dd className="font-mono break-all">
            {message(locale, 'incidents.preview.example.detector')}
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          <dt className="text-muted">
            {message(locale, 'incidents.preview.label.subject')}
          </dt>
          <dd className="font-mono break-all">
            {message(locale, 'incidents.preview.example.subject')}
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          <dt className="text-muted">
            {message(locale, 'incidents.preview.label.evidence')}
          </dt>
          <dd className="font-mono break-all">
            {message(locale, 'incidents.preview.example.evidence')}
          </dd>
        </div>
      </dl>
    </section>
  );
}

/** One segmented row, addressed the same way `FilterBar` addresses a `<select>`. */
function FilterSegment({
  path,
  name,
  label,
  state,
  filters,
  options,
}: {
  readonly path: string;
  readonly name: FilterName;
  readonly label: string;
  readonly state: ReturnType<typeof readViewState>;
  readonly filters: readonly FilterName[];
  readonly options: readonly Omit<SegmentedOption, 'href'>[];
}): ReactNode {
  return (
    <div className="flex flex-col gap-2" data-testid="filter" data-filter={name}>
      <span className="text-micro text-muted font-semibold uppercase tracking-wide">
        {label}
      </span>
      <SegmentedLinks
        label={label}
        selected={state.filters[name] ?? ''}
        options={options.map((option) => ({
          ...option,
          href: hrefFor(path, withFilter(state, name, option.id), filters),
        }))}
      />
    </div>
  );
}

export async function IncidentsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, INCIDENT_ADDRESS);
  const grouped = state.filters[VIEW_PARAM] !== FLAT_VIEW;
  const init = authorised(credential);

  const [incidents, detectors, resources, observations, runs, setup] =
    await Promise.all([
      panelRead('/v1/incidents', () => read('/v1/incidents', init)),
      // Read for the same reason the Detectors screen reads it — to say how
      // many are live — not to drive this panel's own state. A detector read
      // that fails answers "unknown" rather than "none", so a gateway hiccup
      // here cannot make this screen say nothing is watching when it might be.
      panelRead('/v1/detectors', () => read('/v1/detectors', init)),
      // The two reads the footer's detector-coverage card needs — the estate's
      // own degraded/unhealthy resources, and what enabled detectors currently
      // conclude — each one read for the whole page, never per row.
      panelRead('/v1/estate/resources', () => read('/v1/estate/resources', init)),
      panelRead('/v1/observations', () => read('/v1/observations', init)),
      // The headline of whatever run investigated a settled firing — one read
      // for the page, looked up per group rather than fetched per group.
      panelRead('/v1/runs', () => read('/v1/runs', init)),
      readSetupState(credential),
    ]);
  const records = list(dataOf(incidents), 'incidents');

  const states = [
    ...new Set(
      records.map((record) => text(record, 'state')).filter((value) => value !== ''),
    ),
  ].sort();

  const liveDetectors =
    detectors.status === 'ready'
      ? list(dataOf(detectors), 'detectors').filter((record) => flag(record, 'enabled'))
          .length
      : null;

  // The watching cause is the more specific of the two: a deployment can
  // finish its checklist and still have nothing switched on, and the reverse
  // sentence — "finish setting up" — would be advice for something already
  // done. Unknown coverage (the detector read failed) asserts neither.
  const cause = firstCause(
    liveDetectors === null ? null : watchingCause(locale, liveDetectors),
    setupCause(locale, setup, INVESTIGATION_STEP),
  );

  const filtered = records.filter((record) =>
    INCIDENT_FILTERS.every((name) => {
      const value = state.filters[name];
      return !value || text(record, name) === value;
    }),
  );

  const sorted = [...filtered].sort((left, right) => {
    if (state.sort !== '') {
      const order = text(left, state.sort).localeCompare(text(right, state.sort));
      return state.descending ? -order : order;
    }
    const bySeverity = severityRank(left) - severityRank(right);
    return bySeverity !== 0
      ? bySeverity
      : text(right, 'opened_at').localeCompare(text(left, 'opened_at'));
  });

  const rows: readonly ListRow[] = sorted.map((record) => {
    const id = text(record, 'public_id');
    return {
      id,
      href: `/incidents/${id}`,
      cells: [
        { kind: 'text', text: text(record, 'title') },
        { kind: 'status', text: text(record, 'severity') },
        { kind: 'status', text: text(record, 'state') },
        { kind: 'muted', text: text(record, 'detector') },
        {
          kind: 'muted',
          text: text(record, 'opened_at'),
        },
        { kind: 'numeric', text: String(list(record, 'subjects').length) },
      ],
    };
  });

  const groups = groupBySubject(sorted);

  const critical = groups.filter(
    (group) => group.live && group.severity === CRITICAL_SEVERITY,
  ).length;

  // The headline every settled firing with a run may cite, resolved once for
  // the whole page: `run_id` -> the same name `subjectOf` gives every other
  // screen that shows a run, never a second opinion about what a run is
  // called.
  const runHeadlines = new Map<string, string>();
  if (runs.status === 'ready') {
    for (const record of list(dataOf(runs), 'runs')) {
      const runId = text(record, 'run_id');
      if (runId === '') continue;
      const subject = subjectOf(record, locale);
      runHeadlines.set(runId, subject.text);
    }
  }

  const uncoveredCount =
    resources.status === 'ready' && observations.status === 'ready'
      ? degradedFindingsWithoutDetector(
          list(dataOf(resources), 'resources'),
          list(dataOf(observations), 'observations'),
        )
      : 0;

  const showPreview = incidents.status === 'ready' && records.length === 0;

  return (
    <>
      <AreaHeader area={areaFor('incidents')} locale={locale} />

      <div className="flex items-end gap-3 mb-4">
        <FilterSegment
          path="/incidents"
          name="state"
          label={message(locale, 'incidents.filter.state')}
          state={state}
          filters={INCIDENT_ADDRESS}
          options={[
            { id: '', label: message(locale, 'surface.filter.any') },
            ...(states.includes('investigating')
              ? [
                  {
                    id: 'investigating',
                    label: message(locale, 'incidents.filter.state.investigating'),
                  },
                ]
              : []),
            ...(states.includes('resolved')
              ? [
                  {
                    id: 'resolved',
                    label: message(locale, 'incidents.filter.state.resolved'),
                  },
                ]
              : []),
          ]}
        />
        <FilterSegment
          path="/incidents"
          name="severity"
          label={message(locale, 'incidents.filter.severity')}
          state={state}
          filters={INCIDENT_ADDRESS}
          options={[
            { id: '', label: message(locale, 'surface.filter.any') },
            {
              id: CRITICAL_SEVERITY,
              label: message(locale, 'incidents.filter.severity.critical'),
              icon: <span aria-hidden="true" className="icon-inline bg-danger" />,
            },
          ]}
        />
        {groups.length === sorted.length ? null : (
          <FilterSegment
            path="/incidents"
            name={VIEW_PARAM}
            label={message(locale, 'incidents.filter.view')}
            state={state}
            filters={INCIDENT_ADDRESS}
            options={[
              { id: '', label: message(locale, 'incidents.view.grouped') },
              { id: FLAT_VIEW, label: message(locale, 'incidents.view.flat') },
            ]}
          />
        )}
        <span
          data-testid="incident-summary-line"
          className="ml-auto text-small text-muted self-end pb-2"
        >
          {message(locale, 'incidents.header.summary', {
            subjects: groups.length,
            firings: sorted.length,
            critical,
          })}
        </span>
      </div>

      <Panel
        title={message(locale, 'incidents.list.title')}
        titleHidden
        action={
          showPreview ? (
            <Link href="#incident-preview" data-testid="incident-preview-link">
              {message(locale, 'incidents.preview.link')}
            </Link>
          ) : undefined
        }
        state={stateOf(incidents, rows.length === 0)}
        dependency={dependencyOf(incidents)}
        labels={panelLabels(locale, message(locale, 'incidents.list.title'))}
        empty={emptyBecause(
          {
            heading: message(locale, 'incidents.empty.heading'),
            body: message(locale, 'incidents.empty.body'),
            actionLabel: message(locale, 'incidents.empty.action'),
            href: '/signals?tab=observation',
          },
          cause,
        )}
      >
        {grouped ? (
          <IncidentGroupList
            groups={groups}
            locale={locale}
            now={now}
            zone={zone}
            runHeadlines={runHeadlines}
          />
        ) : (
          <RowList
            path="/incidents"
            state={state}
            filters={INCIDENT_ADDRESS}
            labels={rowLabels(locale, message(locale, 'incidents.list.caption'))}
            columns={[
              {
                key: 'title',
                header: message(locale, 'incidents.column.title'),
                sortable: true,
              },
              {
                key: 'severity',
                header: message(locale, 'incidents.column.severity'),
                sortable: true,
                width: 'word',
              },
              {
                key: 'state',
                header: message(locale, 'incidents.column.state'),
                sortable: true,
                width: 'badge',
              },
              {
                key: 'detector',
                header: message(locale, 'incidents.column.detector'),
                width: 'instant',
              },
              {
                key: 'opened_at',
                header: message(locale, 'incidents.column.opened'),
                sortable: true,
                width: 'instant',
              },
              {
                key: 'subjects',
                header: message(locale, 'incidents.column.subjects'),
                numeric: true,
                width: 'measure',
              },
            ]}
            rows={rows}
          />
        )}
      </Panel>
      {showPreview ? <IncidentPreview locale={locale} /> : null}

      {uncoveredCount === 0 ? null : (
        <div
          data-testid="detector-coverage-gap"
          className="mt-4 flex items-center gap-3 rounded-3 edge border-warning bg-warning-bg px-4 py-3"
        >
          <span
            aria-hidden="true"
            className="icon-inline clip-triangle bg-warning shrink-0"
          />
          <p className="text-small">
            {message(locale, 'incidents.coverage.gap', {
              count: uncoveredCount,
            })}
          </p>
          <NextLink
            href="/signals?tab=observation"
            prefetch={false}
            className="ml-auto shrink-0 text-small text-warning hover:underline"
          >
            {message(locale, 'incidents.coverage.action')}
          </NextLink>
        </div>
      )}
    </>
  );
}
