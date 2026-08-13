import type { ReactNode } from 'react';

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

/**
 * What a detector opened, and what happened to it since.
 *
 * Grouped by state and ordered by severity then age, which is the order somebody
 * triages in. The filters are in the address like every other list here, so a
 * link to "everything critical and open" is a link.
 */

export const INCIDENT_FILTERS: readonly FilterName[] = ['state', 'severity'];

/** Most severe first. A list sorted alphabetically by severity is a list nobody reads. */
const SEVERITY_ORDER = ['critical', 'high', 'warning', 'medium', 'low', 'info'];

function severityRank(record: unknown): number {
  const found = SEVERITY_ORDER.indexOf(text(record, 'severity'));
  return found === -1 ? SEVERITY_ORDER.length : found;
}

export async function IncidentsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, INCIDENT_FILTERS);
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

  const states = [...new Set(records.map((record) => text(record, 'state')))].sort();
  const severities = [
    ...new Set(records.map((record) => text(record, 'severity'))),
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
    setupCause(locale, setup),
  );

  const filtered = records.filter((record) =>
    Object.entries(state.filters).every(
      ([name, value]) => text(record, name) === value,
    ),
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
    const id = text(record, 'incident_id');
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

  return (
    <>
      <AreaHeader area={areaFor('incidents')} locale={locale} />

      <FilterBar
        path="/incidents"
        state={state}
        filters={INCIDENT_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={choices}
      />

      <Panel
        title={message(locale, 'incidents.list.title')}
        state={stateOf(incidents, rows.length === 0)}
        dependency={dependencyOf(incidents)}
        labels={panelLabels(locale, message(locale, 'incidents.list.title'))}
        empty={emptyBecause(
          {
            heading: message(locale, 'incidents.empty.heading'),
            body: message(locale, 'incidents.empty.body'),
            actionLabel: message(locale, 'incidents.empty.action'),
            href: '/detectors',
          },
          cause,
        )}
      >
        <RowList
          path="/incidents"
          state={state}
          filters={INCIDENT_FILTERS}
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
            },
            {
              key: 'state',
              header: message(locale, 'incidents.column.state'),
              sortable: true,
            },
            { key: 'detector', header: message(locale, 'incidents.column.detector') },
            {
              key: 'opened_at',
              header: message(locale, 'incidents.column.opened'),
              sortable: true,
            },
            {
              key: 'subjects',
              header: message(locale, 'incidents.column.subjects'),
              numeric: true,
            },
          ]}
          rows={rows}
        />
      </Panel>
    </>
  );
}
