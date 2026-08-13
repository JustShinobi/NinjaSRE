import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { Input } from '@/components/form';
import { timestamp } from '@/i18n/format';
import type { MessageKey } from '@/i18n/en';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { FilterBar } from '../filters';
import { panelLabels, rowLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  countOf,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  number,
  optionalRead,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { RowList, type ListRow } from '../rows';
import { hrefFor, readViewState, withSelection, type FilterName } from '../url-state';
import { UNPLACED, criticalityOf, criticalityRank, zoneOf } from './resources-view';

/**
 * What am I responsible for, and what state is it in?
 *
 * Sorted worst-first by default, so the problems are at the top without anybody
 * filtering for them. `stale` and `absent` are their own states rather than
 * shades of `unhealthy`, because an integration outage and a broken machine
 * demand different responses — and a failed sweep must never make the estate look
 * like a disaster.
 *
 * **The state column is the state the deployment reports** — absence,
 * maintenance and freshness already applied by the endpoint. The console does
 * not derive it, does not age it, and does not translate it: the whole point of
 * "health is derived, not declared" is that exactly one thing derives it, and a
 * second copy of the freshness rule here would disagree with the first the day
 * somebody changed an interval.
 *
 * Utilisation is a meter *and* a number where there is a capacity, and free text
 * where there is not. A bar alone is a shape somebody has to estimate, and "about
 * ninety per cent" is not a figure anybody acts on.
 *
 * **Selecting a row shows where its signals come from, above the table.** The
 * detail used to be appended after a hundred-odd rows, outside the viewport, so
 * a click that worked looked exactly like one that did nothing. It now opens at
 * the top, named, with the way back to the list beside it.
 *
 * Six questions, and for
 * each one either the source that answers it or the integration that would. The
 * one that earns the panel is *pressure*: a container's resource usage is the
 * host's to report, so the row reads "Prometheus, keyed by vmid 100" rather than
 * leaving an investigation to ask inside the guest and get a plausible wrong
 * number. The absences are the same panel's other half — a blank where a log
 * store should be reads as "there are no logs".
 *
 * **The findings sit below, and there are two kinds.** What the declared
 * inventory names and the provider no longer reports, and what an alert named
 * that this estate does not hold. They come from opposite directions and share
 * a shape: neither has a row to mark, so neither would be visible at all if it
 * were only rendered on the resource it lacks.
 */

/**
 * Zone and criticality, not kind and state.
 *
 * Kind and state are what the hypervisor knows. An operator triaging an
 * estate asks "what is in the DMZ" and "what is critical" — and until the
 * declared inventory was read, neither question had an answer to filter on,
 * so the screen offered the two facts it happened to have.
 *
 * State has not gone anywhere: the default sort is still worst-first, and the
 * state column is still there. It is simply not what somebody narrows by.
 *
 * `q` is the fourth: a name search, round-tripped through the address like
 * every other filter here rather than held in component state, so a search
 * survives a reload and a link to it finds the same rows for whoever opens it.
 */
export const RESOURCE_FILTERS: readonly FilterName[] = ['zone', 'criticality', 'q'];

/**
 * Worst first. The order is the triage order, not the alphabet.
 *
 * The endpoint's closed set, in the order somebody triages it. A state this
 * console has not met sorts last and keeps its own word rather than being
 * folded into one it resembles.
 */
const STATE_ORDER = [
  'unhealthy',
  'degraded',
  'unknown',
  'stale',
  'maintenance',
  'absent',
  'healthy',
];

function stateRank(record: unknown): number {
  const found = STATE_ORDER.indexOf(text(record, 'health'));
  return found === -1 ? STATE_ORDER.length : found;
}

/**
 * The largest utilisation reading a resource carries, as a percentage.
 *
 * Read out of `attributes`, which is where an integration that knows what a
 * fill percentage means puts one. The core kinds declare none, so a deployment
 * with nothing connected shows no meter rather than a meter reading nought.
 */
function utilisation(record: unknown): number {
  const attributes: unknown = field(record, 'attributes');
  return Math.max(
    number(attributes, 'volume_percent'),
    number(attributes, 'memory_percent'),
    number(attributes, 'cpu_percent'),
  );
}

/**
 * The message key naming what connects a change to this resource.
 *
 * A closed set with a fallback, because the endpoint's strengths are a closed
 * enumeration and a console that met a new one should say "same window only"
 * rather than render a raw identifier — the cautious reading is the safe one.
 */
function strengthLabel(strength: string): MessageKey {
  if (strength === 'manages_resource') return 'resources.changes.manages';
  if (strength === 'touches_shared_policy') return 'resources.changes.policy';
  return 'resources.changes.coincidence';
}

export async function ResourcesScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, RESOURCE_FILTERS);

  const init = authorised(credential);
  const selection = state.selection;
  const [resources, summary, discovery, unresolved, selected] = await Promise.all([
    panelRead('/v1/estate/resources', () => read('/v1/estate/resources', init)),
    panelRead('/v1/estate/summary', () => read('/v1/estate/summary', init)),
    // Optional: a deployment that has never swept anything has no report, and
    // that is the ordinary state of one nothing is pointed at yet.
    optionalRead('/v1/estate/discovery/report', () =>
      read('/v1/estate/discovery/report', init),
    ),
    // Optional for the same reason, and one more: a deployment nothing has
    // alerted has no findings, which is the ordinary state rather than a fault.
    optionalRead('/v1/estate/unresolved-alert-targets', () =>
      read('/v1/estate/unresolved-alert-targets', init),
    ),
    // Only when a row is selected. The detail read is per resource, and making
    // it on every render of the list would be one request per page view for a
    // panel nobody has opened.
    selection === null
      ? Promise.resolve(undefined)
      : optionalRead('/v1/estate/resources/{resource_id}', () =>
          read('/v1/estate/resources/{resource_id}', {
            ...init,
            params: { resource_id: selection },
          }),
        ),
  ]);
  const signals =
    selected === undefined ? undefined : field(dataOf(selected), 'signals');
  // The corpus's own answer to "what do we already know about this". Empty for
  // most of any estate and for all of one whose corpus has not been synced, so
  // the panel is drawn only when there is something in it — an empty one on
  // every resource would be noise on a screen that is mostly a table.
  const documents = selected === undefined ? [] : list(dataOf(selected), 'documents');
  // What changed underneath it. Unlike the documents, this panel is drawn even
  // when it lists nothing: "no change touched this in the last day" is the
  // finding, and an absent panel would be indistinguishable from a deployment
  // that never looked. It is absent only when the detail carries no block at
  // all, which is a gateway older than the feature rather than a quiet resource.
  const changes =
    selected === undefined ? undefined : field(dataOf(selected), 'changes');
  // What the detail heading calls the selection. The detail read can be refused
  // by an older gateway; the identifier then stands in for the name, because a
  // selection must still visibly change the screen either way.
  const selectedName =
    (selected === undefined
      ? ''
      : text(field(dataOf(selected), 'resource'), 'display_name')) ||
    (selection ?? '');
  const records = list(dataOf(resources), 'resources');

  // Divergence is content, not an error. Two facts come out of the last sweep
  // of each source: which resources the declared inventory does not describe,
  // and which entries it describes that no longer exist. The first marks a row;
  // the second has no row to mark, which is why it gets a panel of its own —
  // "this machine is gone and the file still believes in it" is a finding
  // nobody would ever see if it were only rendered on the resource it lacks.
  const reports = list(dataOf(discovery), 'reports');
  const divergences = reports.flatMap((report) => list(report, 'divergences'));
  const undeclared = new Set(
    divergences
      .filter((entry) => text(entry, 'kind') === 'only_in_provider')
      .map((entry) => text(entry, 'subject')),
  );
  const departed = divergences.filter(
    (entry) => text(entry, 'kind') === 'only_in_file',
  );

  // The third finding on this screen, and the one that comes from the other
  // direction: not "the file names something the provider does not", but
  // "something outside is complaining about a target nothing here holds". Same
  // shape of answer, same reason for a panel — there is no row to mark.
  const unresolvedTargets = list(dataOf(unresolved), 'targets');

  // The vocabulary this estate actually uses, not one this console invents:
  // an operator whose tiers are gold/silver/bronze filters by those words.
  const zones = [...new Set(records.map(zoneOf))].sort();
  const criticalities = [...new Set(records.map(criticalityOf))].filter(Boolean).sort();

  // A name typed into the address, folded for a case that should not matter to
  // the person who typed it.
  const query = (state.filters.q ?? '').trim().toLowerCase();

  const filtered = records.filter((record) => {
    const zone = state.filters.zone;
    const criticality = state.filters.criticality;
    if (zone !== undefined && zoneOf(record) !== zone) return false;
    if (criticality !== undefined && criticalityOf(record) !== criticality)
      return false;
    if (query !== '' && !text(record, 'display_name').toLowerCase().includes(query))
      return false;
    return true;
  });

  const sorted = [...filtered].sort((left, right) => {
    if (state.sort !== '') {
      const order = text(left, state.sort).localeCompare(text(right, state.sort));
      return state.descending ? -order : order;
    }
    // Worst first, and among equally unwell things the ones somebody said
    // matter most. A degraded critical guest outranks a degraded scratch one.
    const byState = stateRank(left) - stateRank(right);
    return byState !== 0 ? byState : criticalityRank(left) - criticalityRank(right);
  });

  const none = message(locale, 'surface.none');

  // A column that is never once populated teaches a reader to stop looking at
  // it — the utilisation meter when nothing has ever reported one, and equally
  // the divergence mark on a deployment whose last sweep found none. Both are
  // decided over what is actually on screen, so filtering to a quiet zone can
  // make either column disappear even when the whole estate has readings.
  const hasUtilisation = sorted.some((record) => utilisation(record) > 0);
  const hasDivergence = sorted.some((record) =>
    undeclared.has(text(record, 'correlation_key')),
  );

  const rows: readonly ListRow[] = sorted.map((record) => {
    const id = text(record, 'resource_id');
    const used = utilisation(record);
    const diverges = undeclared.has(text(record, 'correlation_key'));
    return {
      id,
      href: `/resources?selected=${id}`,
      cells: [
        // The name, and only the name — a sentence appended to an identifier
        // reads as part of it, which is exactly what the divergence mark
        // stopped being once it moved to a column of its own below.
        { kind: 'text', text: text(record, 'display_name') },
        ...(hasDivergence
          ? [
              {
                kind: 'muted' as const,
                text: diverges ? message(locale, 'resources.divergent.mark') : none,
              },
            ]
          : []),
        { kind: 'muted', text: text(record, 'kind') },
        {
          kind: 'muted',
          text:
            zoneOf(record) === UNPLACED
              ? message(locale, 'resources.zone.unplaced')
              : zoneOf(record),
        },
        {
          // The word the operator wrote, never one this console chose for them.
          kind: criticalityOf(record) === '' ? 'muted' : 'status',
          text:
            criticalityOf(record) === ''
              ? message(locale, 'resources.criticality.ungraded')
              : criticalityOf(record),
        },
        { kind: 'status', text: text(record, 'health') },
        ...(hasUtilisation
          ? [
              used > 0
                ? {
                    kind: 'meter' as const,
                    text: text(record, 'display_name'),
                    value: Math.round(used),
                  }
                : { kind: 'muted' as const, text: none },
            ]
          : []),
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
              watched: String(number(dataOf(summary), 'total')),
              healthy: String(countOf(dataOf(summary), 'by_health', 'healthy')),
              // The word in the sentence is "degraded", so the number beside it
              // is the count of resources actually in that state — not
              // `problems`, which is degraded *and* unhealthy folded together.
              // That folding is exactly what left this header unable to add up
              // against the badges below it or the dashboard's own count.
              degraded: String(countOf(dataOf(summary), 'by_health', 'degraded')),
              // Its own number rather than folded into degraded. Broken and
              // degrading are different states with different next actions, and
              // one of them had no count anywhere on this screen.
              unhealthy: String(countOf(dataOf(summary), 'by_health', 'unhealthy')),
            })}
          </span>
        }
      />

      {/* A plain GET form rather than a client filter: the address is still
          the whole of what a view is, so a search survives a reload and a
          link to it finds the same rows for whoever opens it. The other
          filters ride along as hidden fields so typing a name does not drop
          a zone or criticality already chosen. */}
      <form
        method="get"
        action="/resources"
        className="mb-4"
        data-testid="resource-search"
      >
        <Input
          label={message(locale, 'resources.filter.name')}
          name="q"
          type="search"
          defaultValue={state.filters.q ?? ''}
        />
        {state.filters.zone === undefined ? null : (
          <input type="hidden" name="zone" value={state.filters.zone} />
        )}
        {state.filters.criticality === undefined ? null : (
          <input type="hidden" name="criticality" value={state.filters.criticality} />
        )}
        {state.sort === '' ? null : (
          <input
            type="hidden"
            name="sort"
            value={state.descending ? `-${state.sort}` : state.sort}
          />
        )}
        {state.selection === null ? null : (
          <input type="hidden" name="selected" value={state.selection} />
        )}
      </form>

      <FilterBar
        path="/resources"
        state={state}
        filters={RESOURCE_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={[
          {
            name: 'zone',
            label: message(locale, 'resources.filter.zone'),
            options: zones.map((value) => ({
              value,
              label:
                value === UNPLACED ? message(locale, 'resources.zone.unplaced') : value,
            })),
          },
          {
            name: 'criticality',
            label: message(locale, 'resources.filter.criticality'),
            options: criticalities.map((value) => ({ value, label: value })),
          },
        ]}
      />

      {/* The detail sits above the table, not appended after it. Below a
          hundred-odd rows it renders outside the viewport, and a click that
          worked is indistinguishable from one that did nothing. The heading
          names what was opened, and the link beside it is the way back —
          carrying the rest of the view, so closing the detail does not also
          discard the filters. */}
      {selection === null ? null : (
        <div className="flex items-baseline gap-3" data-testid="resource-detail-header">
          <h2 className="text-section">{selectedName}</h2>
          <Link
            href={hrefFor('/resources', withSelection(state, null), RESOURCE_FILTERS)}
            data-testid="resource-detail-back"
          >
            {message(locale, 'resources.detail.back')}
          </Link>
        </div>
      )}

      {signals === undefined ? null : (
        <Panel
          title={message(locale, 'resources.signals.title')}
          state="ready"
          labels={panelLabels(locale, message(locale, 'resources.signals.title'))}
          empty={{
            heading: message(locale, 'resources.signals.title'),
            body: message(locale, 'resources.signals.body'),
            actionLabel: message(locale, 'resources.empty.action'),
            href: '/configuration',
          }}
        >
          <ul className="flex flex-col gap-2 text-small" data-testid="resource-signals">
            <li className="text-meta text-muted">
              {message(locale, 'resources.signals.body')}
            </li>
            {list(signals, 'sources').map((entry) => (
              <li
                key={text(entry, 'question')}
                data-testid="signal-source"
                data-question={text(entry, 'question')}
                className="flex flex-col gap-1"
              >
                <span>
                  <span className="text-strong">{text(entry, 'question')}</span>{' '}
                  <span className="text-muted">
                    {text(entry, 'integration')}
                    {text(entry, 'key') === ''
                      ? ''
                      : ` · ${text(entry, 'keyed_by')} ${text(entry, 'key')}`}
                  </span>
                </span>
                <span className="text-meta text-muted">{text(entry, 'detail')}</span>
              </li>
            ))}
            {list(signals, 'missing').map((entry) => (
              <li
                key={text(entry, 'question')}
                data-testid="signal-missing"
                data-question={text(entry, 'question')}
                className="flex flex-col gap-1"
              >
                <span>
                  <span className="text-strong">{text(entry, 'question')}</span>{' '}
                  <span className="text-warning">
                    {message(locale, 'resources.signals.missing')}
                  </span>
                </span>
                <span className="text-meta text-muted">{text(entry, 'why')}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {documents.length === 0 ? null : (
        <Panel
          title={message(locale, 'resources.documents.title')}
          state="ready"
          labels={panelLabels(locale, message(locale, 'resources.documents.title'))}
          empty={{
            heading: message(locale, 'resources.documents.title'),
            body: message(locale, 'resources.documents.body'),
            actionLabel: message(locale, 'resources.empty.action'),
            href: '/knowledge',
          }}
        >
          <ul
            className="flex flex-col gap-2 text-small"
            data-testid="resource-documents"
          >
            <li className="text-meta text-muted">
              {message(locale, 'resources.documents.body')}
            </li>
            {documents.map((entry) => (
              <li
                key={text(entry, 'document_id')}
                data-testid="resource-document"
                data-document-type={text(entry, 'document_type')}
                className="flex flex-col gap-1"
              >
                <span>
                  <span className="text-strong">{text(entry, 'title')}</span>{' '}
                  <span className="text-muted">{text(entry, 'document_type')}</span>
                </span>
                <span className="text-meta text-muted">
                  {text(entry, 'location')}
                  {text(entry, 'matched') === ''
                    ? ''
                    : ` · ${text(entry, 'matched_on')} ${text(entry, 'matched')}`}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {changes === undefined ? null : (
        <Panel
          title={message(locale, 'resources.changes.title')}
          state="ready"
          labels={panelLabels(locale, message(locale, 'resources.changes.title'))}
          empty={{
            heading: message(locale, 'resources.changes.title'),
            body: message(locale, 'resources.changes.body'),
            actionLabel: message(locale, 'resources.empty.action'),
            href: '/configuration',
          }}
        >
          <ul
            className="flex flex-col gap-2 text-small"
            data-testid="resource-changes"
            data-answered={String(flag(changes, 'answered'))}
          >
            {/* The statement first and always. It is the same sentence the
                investigation's own report carries, and it is the whole panel
                when nothing is listed. */}
            <li className="text-meta text-muted">{text(changes, 'statement')}</li>
            {list(changes, 'entries').map((entry) => (
              <li
                key={text(entry, 'change_id')}
                data-testid="resource-change"
                data-strength={text(entry, 'strength')}
                data-applied={String(flag(entry, 'applied'))}
                className="flex flex-col gap-1"
              >
                <span>
                  <span className="text-strong">{text(entry, 'message')}</span>{' '}
                  <span className="text-muted">
                    {text(entry, 'change_id')}
                    {text(entry, 'author') === '' ? '' : ` · ${text(entry, 'author')}`}
                    {` · ${timestamp(locale, text(entry, 'instant'), now, zone).relative}`}
                  </span>
                </span>
                <span className="text-meta text-muted">
                  <span
                    className={
                      text(entry, 'strength') === 'manages_resource'
                        ? 'text-strong'
                        : 'text-muted'
                    }
                  >
                    {message(locale, strengthLabel(text(entry, 'strength')))}
                  </span>
                  {flag(entry, 'applied')
                    ? ''
                    : ` · ${message(locale, 'resources.changes.unapplied')}`}
                  {text(entry, 'component') === ''
                    ? ''
                    : ` · ${text(entry, 'component')}`}
                </span>
                <span className="text-meta text-muted">{text(entry, 'why')}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

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
              key: 'display_name',
              header: message(locale, 'resources.column.name'),
              sortable: true,
            },
            // Its own column, drawn only when the current view actually holds
            // a divergence — the same "not a column nobody ever fills"
            // discipline the utilisation column below follows.
            ...(hasDivergence
              ? [
                  {
                    key: 'divergent',
                    header: message(locale, 'resources.divergent.mark'),
                  },
                ]
              : []),
            {
              key: 'kind',
              header: message(locale, 'resources.column.kind'),
              sortable: true,
            },
            {
              key: 'zone',
              header: message(locale, 'resources.column.zone'),
              sortable: true,
            },
            {
              key: 'criticality',
              header: message(locale, 'resources.column.criticality'),
              sortable: true,
            },
            {
              key: 'health',
              header: message(locale, 'resources.column.state'),
              sortable: true,
            },
            // Drawn only when something in the current view has a reading.
            // Every row saying "Not recorded" is not a column, it is a lesson
            // that this table's columns are not worth reading.
            ...(hasUtilisation
              ? [
                  {
                    key: 'utilisation',
                    header: message(locale, 'resources.column.utilisation'),
                  },
                ]
              : []),
            {
              key: 'last_seen_at',
              header: message(locale, 'resources.column.lastSeen'),
            },
          ]}
          rows={rows}
        />
      </Panel>

      {unresolvedTargets.length === 0 ? null : (
        <Panel
          title={message(locale, 'resources.unresolved.title')}
          state={stateOf(unresolved, false)}
          dependency={dependencyOf(unresolved)}
          labels={panelLabels(locale, message(locale, 'resources.unresolved.title'))}
          empty={{
            heading: message(locale, 'resources.unresolved.title'),
            body: message(locale, 'resources.unresolved.body'),
            actionLabel: message(locale, 'resources.empty.action'),
            href: '/configuration',
          }}
        >
          <ul
            className="flex flex-col gap-1 text-small"
            data-testid="unresolved-targets"
          >
            <li className="text-meta text-muted">
              {message(locale, 'resources.unresolved.body')}
            </li>
            {unresolvedTargets.map((entry) => (
              <li
                key={`${text(entry, 'label')}:${text(entry, 'value')}`}
                data-testid="unresolved-target-entry"
                className="flex flex-col gap-1"
              >
                <span>
                  <span className="text-strong">{text(entry, 'value')}</span>{' '}
                  <span className="text-muted">
                    {text(entry, 'label')}
                    {text(entry, 'zone') === '' ? '' : ` · ${text(entry, 'zone')}`}
                    {` · ${text(entry, 'alert_name')}`}
                  </span>
                </span>
                <span className="text-meta text-muted">{text(entry, 'why')}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {departed.length === 0 ? null : (
        <Panel
          title={message(locale, 'resources.departed.title')}
          state={stateOf(discovery, false)}
          dependency={dependencyOf(discovery)}
          labels={panelLabels(locale, message(locale, 'resources.departed.title'))}
          empty={{
            heading: message(locale, 'resources.departed.title'),
            body: message(locale, 'resources.departed.body'),
            actionLabel: message(locale, 'resources.empty.action'),
            href: '/configuration',
          }}
        >
          <ul className="flex flex-col gap-1 text-small" data-testid="departed">
            <li className="text-meta text-muted">
              {message(locale, 'resources.departed.body')}
            </li>
            {departed.map((entry) => (
              <li key={text(entry, 'subject')} data-testid="departed-entry">
                <span className="text-strong">{text(entry, 'subject')}</span>{' '}
                <span className="text-muted">{text(entry, 'detail')}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </>
  );
}
