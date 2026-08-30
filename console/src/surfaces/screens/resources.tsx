import type { ReactNode } from 'react';
import NextLink from 'next/link';

import { Link } from '@/components/action';
import { Input } from '@/components/form';
import { humaniseIdentifier, timestamp } from '@/i18n/format';
import type { MessageKey } from '@/i18n/en';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { readSetupState } from '../emptiness';
import { requestedSetupReturn, SetupReturnBanner } from '../first-run/return-banner';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  counts,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  optionalRead,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { hrefFor, readViewState, withFilter, withSelection, type FilterName } from '../url-state';
import { UNPLACED, criticalityOf, zoneOf } from './resources-view';
import { groupByNode, healthSegments, unhealthySynthesis } from './resources-grouping';

/**
 * What am I responsible for, and what state is it in?
 *
 * Answered on first paint, without interaction: a segmented health bar with a
 * clickable legend, sectioned by the node that hosts each resource — worst
 * section first, worst resource first inside it — and a synthesis line above
 * everything when three or more unhealthy resources share a node, a kind and
 * a start window. Every one of those reads the single listing response;
 * nothing here computes a second request for what the first already carried.
 *
 * **The state a card shows is the state the deployment reports** — absence,
 * maintenance and freshness already applied by the endpoint. The console does
 * not derive it, does not age it, and does not translate it.
 *
 * **Selecting a card shows where its signals come from, above the sections.**
 * Six questions, and for each one either the source that answers it or the
 * integration that would.
 *
 * **The findings sit below, and there are two kinds.** What the declared
 * inventory names and the provider no longer reports, and what an alert named
 * that this estate does not hold.
 */

/** Every dimension this screen narrows by, in the address. */
export const RESOURCE_FILTERS: readonly FilterName[] = [
  'zone',
  'criticality',
  'health',
  'kind',
  'q',
];

/** The two states represented by the legend's own "unhealthy" entry. */
const PROBLEM_HEALTH = new Set(['degraded', 'unhealthy']);

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

/** Which token colours a health's mark, and what shape it draws. */
const HEALTH_MARK: Readonly<Record<string, { readonly role: string; readonly circle: boolean }>> = {
  healthy: { role: 'bg-success', circle: true },
  unhealthy: { role: 'bg-danger', circle: false },
  degraded: { role: 'bg-warning', circle: false },
  unknown: { role: 'bg-neutral', circle: true },
  stale: { role: 'bg-neutral', circle: true },
  maintenance: { role: 'bg-info', circle: false },
  absent: { role: 'bg-neutral', circle: true },
};

function HealthMark({ health }: { readonly health: string }): ReactNode {
  const mark = HEALTH_MARK[health] ?? { role: 'bg-neutral', circle: true };
  return (
    <span
      aria-hidden="true"
      className={`icon-inline shrink-0 ${mark.role} ${mark.circle ? 'rounded-full' : ''}`}
    />
  );
}

/** The header's own bar: one proportional segment per health value present. */
function HealthBar({
  locale,
  breakdown,
  state,
  path,
  filters,
}: {
  readonly locale: SurfaceContext['locale'];
  readonly breakdown: Readonly<Record<string, number>>;
  readonly state: ReturnType<typeof readViewState>;
  readonly path: string;
  readonly filters: readonly FilterName[];
}): ReactNode {
  const segments = healthSegments(breakdown);
  const total = segments.reduce((sum, segment) => sum + segment.count, 0);
  if (total === 0) return null;
  return (
    <div className="flex flex-col gap-2" data-testid="health-bar">
      <div className="flex h-3 overflow-hidden rounded-4 gap-1">
        {segments.map((segment) => (
          <span
            key={segment.health}
            data-testid="health-segment"
            data-health={segment.health}
            className={(HEALTH_MARK[segment.health] ?? HEALTH_MARK.unknown)?.role}
            style={{ flexGrow: segment.count, flexBasis: 0 }}
          />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-5 text-small">
        {segments.map((segment) => (
          <NextLink
            key={segment.health}
            href={hrefFor(path, withFilter(state, 'health', segment.health), filters)}
            prefetch={false}
            data-testid="health-legend-item"
            data-health={segment.health}
            className="flex items-center gap-2 hover:underline"
          >
            <HealthMark health={segment.health} />
            {message(locale, 'resources.summary.legend', {
              count: segment.count,
              health: message(locale, `status.resource.${segment.health}` as MessageKey),
            })}
          </NextLink>
        ))}
      </div>
    </div>
  );
}

/** One resource, as the grid draws it. */
function ResourceCard({
  locale,
  now,
  zone,
  state,
  filters,
  resource,
}: {
  readonly locale: SurfaceContext['locale'];
  readonly now: Date;
  readonly zone: string;
  readonly state: ReturnType<typeof readViewState>;
  readonly filters: readonly FilterName[];
  readonly resource: unknown;
}): ReactNode {
  const health = text(resource, 'health');
  const id = text(resource, 'resource_id');
  const unhealthySince = text(resource, 'unhealthy_since');
  return (
    <NextLink
      href={hrefFor('/resources', withSelection(state, id), filters)}
      prefetch={false}
      data-testid="resource-card"
      data-health={health}
      className={`flex flex-col gap-2 rounded-3 edge p-3 motion-hover hover:border-strong ${health === 'unhealthy' ? 'border-danger' : 'border-border'}`}
    >
      <span className="flex items-center gap-2">
        <span className="text-small font-medium min-w-0 truncate" data-testid="resource-card-name">
          {text(resource, 'display_name')}
        </span>
        <span className="ml-auto shrink-0">
          <HealthMark health={health} />
        </span>
      </span>
      <span className="flex items-center gap-2 text-micro text-muted">
        <span>{humaniseIdentifier(text(resource, 'kind'))}</span>
        <span>·</span>
        <span>
          {message(locale, 'resources.card.lastSeen', {
            when: timestamp(locale, text(resource, 'last_seen_at'), now, zone).relative,
          })}
        </span>
        {health === 'unhealthy' && unhealthySince !== '' ? (
          <span className="ml-auto shrink-0 text-danger" data-testid="resource-unhealthy-duration">
            {message(locale, 'resources.card.unhealthySince', {
              since: timestamp(locale, unhealthySince, now, zone).relative,
            })}
          </span>
        ) : null}
      </span>
    </NextLink>
  );
}

export async function ResourcesScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone, search } = context;
  const state = readViewState(search, RESOURCE_FILTERS);

  const init = authorised(credential);
  const selection = state.selection;
  const [resources, summary, discovery, unresolved, selected, setup] =
    await Promise.all([
      panelRead('/v1/estate/resources', () => read('/v1/estate/resources', init)),
      panelRead('/v1/estate/summary', () => read('/v1/estate/summary', init)),
      optionalRead('/v1/estate/discovery/report', () =>
        read('/v1/estate/discovery/report', init),
      ),
      optionalRead('/v1/estate/unresolved-alert-targets', () =>
        read('/v1/estate/unresolved-alert-targets', init),
      ),
      selection === null
        ? Promise.resolve(undefined)
        : optionalRead('/v1/estate/resources/{resource_id}', () =>
            read('/v1/estate/resources/{resource_id}', {
              ...init,
              params: { resource_id: selection },
            }),
          ),
      readSetupState(credential),
    ]);
  const returnRequested = requestedSetupReturn(search.get('return'));
  const signals =
    selected === undefined ? undefined : field(dataOf(selected), 'signals');
  const documents = selected === undefined ? [] : list(dataOf(selected), 'documents');
  const changes =
    selected === undefined ? undefined : field(dataOf(selected), 'changes');
  const selectedName =
    (selected === undefined
      ? ''
      : text(field(dataOf(selected), 'resource'), 'display_name')) ||
    (selection ?? '');
  const records = list(dataOf(resources), 'resources');

  const reports = list(dataOf(discovery), 'reports');
  const divergences = reports.flatMap((report) => list(report, 'divergences'));
  const departed = divergences.filter(
    (entry) => text(entry, 'kind') === 'only_in_file',
  );
  const unresolvedTargets = list(dataOf(unresolved), 'targets');

  const kinds = [...new Set(records.map((record) => text(record, 'kind')))]
    .filter(Boolean)
    .sort();

  const query = (state.filters.q ?? '').trim().toLowerCase();

  const filtered = records.filter((record) => {
    const zone = state.filters.zone;
    const criticality = state.filters.criticality;
    const health = state.filters.health;
    const kind = state.filters.kind;
    if (zone !== undefined && zoneOf(record) !== zone) return false;
    if (criticality !== undefined && criticalityOf(record) !== criticality) return false;
    if (kind !== undefined && text(record, 'kind') !== kind) return false;
    if (health === 'problem' && !PROBLEM_HEALTH.has(text(record, 'health'))) return false;
    if (health !== undefined && health !== 'problem' && text(record, 'health') !== health)
      return false;
    if (query !== '' && !text(record, 'display_name').toLowerCase().includes(query))
      return false;
    return true;
  });

  const sections = groupByNode(filtered);
  const synthesis = unhealthySynthesis(filtered);
  const hasZone = records.some((record) => zoneOf(record) !== UNPLACED);
  const hasCriticality = records.some((record) => criticalityOf(record) !== '');

  return (
    <>
      <AreaHeader area={areaFor('resources')} locale={locale} />

      <SetupReturnBanner locale={locale} setup={setup} requested={returnRequested} />

      <div className="flex flex-col gap-4 mb-5">
        <HealthBar
          locale={locale}
          breakdown={counts(dataOf(summary), 'by_health').reduce<Record<string, number>>(
            (map, [health, value]) => ({ ...map, [health]: value }),
            {},
          )}
          state={state}
          path="/resources"
          filters={RESOURCE_FILTERS}
        />

        <div className="flex items-center gap-3 flex-wrap">
          <form method="get" action="/resources" data-testid="resource-search">
            <Input
              label={message(locale, 'resources.filter.name')}
              name="q"
              type="search"
              defaultValue={state.filters.q ?? ''}
            />
            {state.filters.health === undefined ? null : (
              <input type="hidden" name="health" value={state.filters.health} />
            )}
            {state.filters.kind === undefined ? null : (
              <input type="hidden" name="kind" value={state.filters.kind} />
            )}
          </form>
          <div className="flex items-center gap-2 flex-wrap">
            <NextLink
              href={hrefFor('/resources', withFilter(state, 'kind', ''), RESOURCE_FILTERS)}
              prefetch={false}
              data-testid="type-chip"
              className={`rounded-full px-3 py-1 text-small edge ${state.filters.kind === undefined ? 'bg-accent-bg text-accent border-accent' : 'text-muted'}`}
            >
              {message(locale, 'resources.filter.kind.any')}
            </NextLink>
            {kinds.map((kind) => (
              <NextLink
                key={kind}
                href={hrefFor('/resources', withFilter(state, 'kind', kind), RESOURCE_FILTERS)}
                prefetch={false}
                data-testid="type-chip"
                className={`rounded-full px-3 py-1 text-small edge ${state.filters.kind === kind ? 'bg-accent-bg text-accent border-accent' : 'text-muted'}`}
              >
                {humaniseIdentifier(kind)}{' '}
                <span className="font-mono text-micro text-muted">
                  {records.filter((record) => text(record, 'kind') === kind).length}
                </span>
              </NextLink>
            ))}
          </div>
        </div>

        {synthesis.map((batch) => (
          <div
            key={`${batch.nodeId}::${batch.kind}`}
            data-testid="unhealthy-synthesis"
            className="flex items-center gap-3 rounded-3 edge border-danger bg-danger-bg px-4 py-3"
          >
            <HealthMark health="unhealthy" />
            <p className="text-small">
              {message(locale, 'resources.synthesis.line', {
                count: batch.count,
                kind: humaniseIdentifier(batch.kind),
                node: batch.nodeName || message(locale, 'resources.node.none'),
                since: timestamp(locale, batch.since, now, zone).relative,
              })}
            </p>
            <a
              href={`/runs?prefill=${encodeURIComponent(
                message(locale, 'resources.synthesis.objective', {
                  count: batch.count,
                  kind: humaniseIdentifier(batch.kind),
                  node: batch.nodeName || message(locale, 'resources.node.none'),
                  since: timestamp(locale, batch.since, now, zone).absolute,
                }),
              )}`}
              className="ml-auto shrink-0 text-small text-danger hover:underline"
            >
              {message(locale, 'resources.synthesis.action')}
            </a>
          </div>
        ))}

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
            <ul className="flex flex-col gap-2 text-small" data-testid="resource-documents">
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
                    {text(entry, 'component') === '' ? '' : ` · ${text(entry, 'component')}`}
                  </span>
                  <span className="text-meta text-muted">{text(entry, 'why')}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <Panel
          title={message(locale, 'resources.list.title')}
          titleHidden
          state={stateOf(resources, sections.length === 0)}
          dependency={dependencyOf(resources)}
          labels={panelLabels(locale, message(locale, 'resources.list.title'))}
          empty={{
            heading: message(locale, 'resources.empty.heading'),
            body: message(locale, 'resources.empty.body'),
            actionLabel: message(locale, 'resources.empty.action'),
            href: '/configuration',
          }}
        >
          <div className="flex flex-col gap-5">
            {sections.map((section) => (
              <div
                key={section.nodeId || 'none'}
                data-testid="node-section"
                data-has-unhealthy={section.hasUnhealthy ? 'true' : 'false'}
                className="flex flex-col gap-2"
              >
                <div className="flex items-center gap-2">
                  <span className="text-strong" data-testid="node-section-name">
                    {section.nodeName || message(locale, 'resources.node.none')}
                  </span>
                  {section.hasUnhealthy ? (
                    <span className="flex items-center gap-1 text-small text-danger">
                      <HealthMark health="unhealthy" />
                      {message(locale, 'resources.node.unhealthyCount', {
                        count: section.resources.filter((entry) =>
                          PROBLEM_HEALTH.has(text(entry, 'health')),
                        ).length,
                      })}
                    </span>
                  ) : null}
                  <span className="text-micro text-muted" data-testid="node-section-count">
                    {message(locale, 'resources.node.count', { count: section.resources.length })}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {section.resources.map((resource) => (
                    <ResourceCard
                      key={text(resource, 'resource_id')}
                      locale={locale}
                      now={now}
                      zone={zone}
                      state={state}
                      filters={RESOURCE_FILTERS}
                      resource={resource}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        {hasZone && hasCriticality ? null : (
          <div
            data-testid="placement-warning"
            className="flex items-center gap-3 rounded-3 edge border-warning bg-warning-bg px-4 py-3"
          >
            <span aria-hidden="true" className="icon-inline clip-triangle bg-warning shrink-0" />
            <p className="text-small">
              {message(
                locale,
                hasZone
                  ? 'resources.none.graded'
                  : hasCriticality
                    ? 'resources.none.placed'
                    : 'resources.none.placedOrGraded',
              )}
            </p>
            <NextLink
              href="/configuration"
              prefetch={false}
              className="ml-auto shrink-0 text-small text-warning hover:underline"
            >
              {message(locale, 'resources.none.action')}
            </NextLink>
          </div>
        )}

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
            <ul className="flex flex-col gap-1 text-small" data-testid="unresolved-targets">
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
      </div>
    </>
  );
}
