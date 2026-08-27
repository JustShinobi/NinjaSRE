import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { Badge } from '@/components/status';
import { timestamp } from '@/i18n/format';
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
import { FilterBar, type FilterChoice } from '../filters';
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
import { readViewState, type FilterName } from '../url-state';
import { IncidentGroupList } from '../incident-group-list';
import { groupBySubject } from '../incident-groups';

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

export async function IncidentsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, INCIDENT_ADDRESS);
  const grouped = state.filters[VIEW_PARAM] !== FLAT_VIEW;
  const init = authorised(credential);

  const [incidents, detectors, setup] = await Promise.all([
    panelRead('/v1/incidents', () => read('/v1/incidents', init)),
    // Read for the same reason the Detectors screen reads it — to say how
    // many are live — not to drive this panel's own state. A detector read
    // that fails answers "unknown" rather than "none", so a gateway hiccup
    // here cannot make this screen say nothing is watching when it might be.
    panelRead('/v1/detectors', () => read('/v1/detectors', init)),
    readSetupState(credential),
  ]);
  const records = list(dataOf(incidents), 'incidents');

  const states = [
    ...new Set(
      records.map((record) => text(record, 'state')).filter((value) => value !== ''),
    ),
  ].sort();
  const severities = [
    ...new Set(
      records.map((record) => text(record, 'severity')).filter((value) => value !== ''),
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
          text: timestamp(locale, text(record, 'opened_at'), now, zone).relative,
        },
        { kind: 'numeric', text: String(list(record, 'subjects').length) },
      ],
    };
  });

  // A choice with no value beside "Any" filters nothing — it is furniture, not
  // a control — so it is left out rather than shown disabled with one option
  // nobody can act on.
  const choices: readonly FilterChoice[] = [
    {
      name: 'state',
      label: message(locale, 'incidents.filter.state'),
      options: states.map((value) => ({ value, label: value })),
    },
    {
      name: 'severity',
      label: message(locale, 'incidents.filter.severity'),
      options: severities.map((value) => ({ value, label: value })),
    },
  ].filter((choice) => choice.options.length > 0);

  const groups = groupBySubject(sorted);

  // The view is offered beside the filters because it belongs to the same
  // address and is set the same way — and only when it would change what is on
  // screen. A listing where every incident is its own cause folds to the same
  // rows either way, so offering to reshape it is the furniture this screen
  // already refuses to draw for a filter with one option.
  const shaped: readonly FilterChoice[] =
    groups.length === sorted.length
      ? choices
      : [
          ...choices,
          {
            name: VIEW_PARAM,
            label: message(locale, 'incidents.filter.view'),
            unsetLabel: message(locale, 'incidents.view.grouped'),
            options: [
              { value: FLAT_VIEW, label: message(locale, 'incidents.view.flat') },
            ],
          },
        ];
  const showPreview = incidents.status === 'ready' && records.length === 0;

  return (
    <>
      <AreaHeader area={areaFor('incidents')} locale={locale} />

      <FilterBar
        path="/incidents"
        state={state}
        filters={INCIDENT_ADDRESS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={shaped}
      />

      <Panel
        title={message(locale, 'incidents.list.title')}
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
          <IncidentGroupList groups={groups} locale={locale} now={now} zone={zone} />
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
    </>
  );
}
