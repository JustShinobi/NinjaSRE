import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { formatNumber } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  number,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';

/**
 * What this deployment may do on its own, and why.
 *
 * The rules table is the whole screen and it is read in **resolution order** —
 * least specific first — because that is the order the deployment reads them in
 * and an operator checking "which of these wins" should not have to reconstruct
 * the precedence from the scopes.
 *
 * The footer is not decoration and stays whatever the table holds. Absence of a
 * rule resolves to propose-only, and an operator reading an empty table has to
 * know whether empty means "anything goes" or "nothing happens without me".
 * Guessing the permissive answer is the one direction this must never be wrong
 * in, so the screen says it rather than implying it.
 *
 * The bounds beside it are the four no level overrides. They are shown even
 * when the table is full, because "restarting is autonomous here" and "and
 * nothing runs between 01:00 and 04:00" are both true and an operator who read
 * only the first would be surprised at two in the morning.
 *
 * Every one of those readings is *at a node*, so the node is resolved before
 * anything is asked for. A deployment with no organisation tree yet resolves to
 * none, and then nothing is asked at all: a policy request with no subject is a
 * path with a brace still in it, which the client refuses and which used to take
 * this route down before an operator had any way to choose a node.
 */

export const AUTONOMY_FILTERS: readonly FilterName[] = ['node'];

/** Least specific first, which is the order resolution considers them in. */
const SCOPE_ORDER = [
  'deployment',
  'team',
  'resource_kind',
  'labels',
  'capability',
  'resource',
  'capability_resource',
];

/** The phrase a scope reads as, assembled from the fields the API sends. */
function matcherOf(scope: unknown): string {
  const kind = text(scope, 'kind');
  if (kind === 'deployment') return '—';
  if (kind === 'team') return text(scope, 'team_node_id');
  if (kind === 'resource_kind') return text(scope, 'resource_kind');
  if (kind === 'labels') {
    const labels = field(scope, 'labels');
    if (typeof labels !== 'object' || labels === null) return '—';
    return Object.entries(labels)
      .map(([name, value]) => `${name}=${String(value)}`)
      .sort()
      .join(', ');
  }
  if (kind === 'capability') return text(scope, 'capability');
  if (kind === 'resource') return text(scope, 'resource_id');
  return `${text(scope, 'capability')} on ${text(scope, 'resource_id')}`;
}

function specificityOf(rule: unknown): number {
  const found = SCOPE_ORDER.indexOf(text(field(rule, 'scope'), 'kind'));
  return found === -1 ? SCOPE_ORDER.length : found;
}

export async function AutonomyScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, AUTONOMY_FILTERS);
  const init = authorised(credential);

  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const nodeId = resolveNode(state, viewer, placedTree(dataOf(tree)));

  // Nothing empty, ready: the panels below then render their own empty state,
  // which says there is no policy here and offers the way to make one.
  const nothing = { status: 'ready' as const, data: {} as unknown };

  const policy =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/autonomy/policy/{node_id}', () =>
          read('/v1/autonomy/policy/{node_id}', {
            ...init,
            params: { node_id: nodeId },
          }),
        );
  const bounds =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/autonomy/policy/{node_id}/bounds', () =>
          read('/v1/autonomy/policy/{node_id}/bounds', {
            ...init,
            params: { node_id: nodeId },
          }),
        );

  const rules = [...list(dataOf(policy), 'rules')].sort(
    (left, right) => specificityOf(left) - specificityOf(right),
  );
  const simulated = flag(dataOf(policy), 'dry_run');
  const stopped = flag(dataOf(bounds), 'stopped');
  const freezes = list(dataOf(bounds), 'freezes');
  const budgets = list(dataOf(bounds), 'budgets');
  const overrides = list(dataOf(bounds), 'overrides');

  return (
    <>
      <AreaHeader
        area={areaFor('autonomy')}
        locale={locale}
        // No crumb for a deployment that resolved to no node: a breadcrumb
        // whose last step is blank reads as a page that lost its subject.
        nested={nodeId === '' ? [] : [{ label: nodeId }]}
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0">
          <Panel
            title={message(locale, 'autonomy.rules.title')}
            state={stateOf(policy, rules.length === 0)}
            dependency={dependencyOf(policy)}
            labels={panelLabels(locale, message(locale, 'autonomy.rules.title'))}
            empty={{
              heading: message(locale, 'autonomy.empty.heading'),
              body: message(locale, 'autonomy.empty.body'),
              actionLabel: message(locale, 'autonomy.empty.action'),
              href: '/configuration',
            }}
          >
            <div className="w-full overflow-x-auto">
              <table className="w-full text-small">
                <caption className="sr-only">
                  {message(locale, 'autonomy.rules.title')}
                </caption>
                <thead>
                  <tr>
                    {[
                      message(locale, 'autonomy.column.scope'),
                      message(locale, 'autonomy.column.matcher'),
                      message(locale, 'autonomy.column.level'),
                      message(locale, 'autonomy.column.risk'),
                    ].map((header) => (
                      <th
                        key={header}
                        scope="col"
                        className="text-left text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
                      >
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule, position) => {
                    const scope = field(rule, 'scope');
                    const level = text(rule, 'level');
                    return (
                      <tr
                        key={`${text(scope, 'kind')}-${String(position)}`}
                        data-testid="autonomy-rule"
                        data-level={level}
                      >
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                          {text(scope, 'kind')}
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0 break-all">
                          {matcherOf(scope)}
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                          <Badge status={level} />
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                          {level === 'act_on_low_risk' ? text(rule, 'risk_bound') : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
          <p data-testid="autonomy-footer" className="text-meta text-muted mt-3">
            {message(locale, 'autonomy.footer')}
          </p>
          {simulated ? (
            <p data-testid="autonomy-dry-run" className="text-meta text-muted mt-2">
              {message(locale, 'autonomy.dry_run')}
            </p>
          ) : null}
        </div>

        <div className="min-w-0 flex flex-col gap-5">
          <Panel
            title={message(locale, 'autonomy.bounds.title')}
            state={stateOf(
              bounds,
              !stopped &&
                freezes.length === 0 &&
                budgets.length === 0 &&
                overrides.length === 0,
            )}
            dependency={dependencyOf(bounds)}
            labels={panelLabels(locale, message(locale, 'autonomy.bounds.title'))}
            empty={{
              heading: message(locale, 'autonomy.empty.heading'),
              body: message(locale, 'autonomy.empty.body'),
              actionLabel: message(locale, 'autonomy.empty.action'),
              href: '/configuration',
            }}
          >
            <dl className="flex flex-col gap-2 text-small">
              {stopped ? (
                <div className="flex items-center gap-3" data-testid="autonomy-stopped">
                  <dt className="font-mono min-w-0 truncate">
                    {message(locale, 'autonomy.bound.stopped')}
                  </dt>
                  <dd className="ml-auto min-w-0 truncate">
                    {text(dataOf(bounds), 'stop_reason')}
                  </dd>
                </div>
              ) : null}
              {freezes.map((freeze) => (
                <div
                  key={text(freeze, 'name')}
                  className="flex items-center gap-3"
                  data-testid="bound"
                  data-bound="freeze"
                >
                  <dt className="font-mono min-w-0 truncate">{text(freeze, 'name')}</dt>
                  <dd className="ml-auto flex items-center gap-2 tabular-nums">
                    {text(freeze, 'start')}–{text(freeze, 'end')}{' '}
                    {text(freeze, 'timezone')}
                  </dd>
                </div>
              ))}
              {budgets.map((budget) => (
                <div
                  key={text(budget, 'name')}
                  className="flex items-center gap-3"
                  data-testid="bound"
                  data-bound="budget"
                >
                  <dt className="font-mono min-w-0 truncate">{text(budget, 'name')}</dt>
                  <dd className="ml-auto flex items-center gap-2 tabular-nums">
                    {formatNumber(locale, number(budget, 'limit'))} /{' '}
                    {text(budget, 'counted_by')}
                  </dd>
                </div>
              ))}
              {overrides.map((override) => (
                <div
                  key={text(override, 'name')}
                  className="flex items-center gap-3"
                  data-testid="bound"
                  data-bound="override"
                >
                  <dt className="font-mono min-w-0 truncate">
                    {text(override, 'name')}
                  </dt>
                  <dd className="ml-auto flex items-center gap-2">
                    <Badge status={text(override, 'level')} />
                  </dd>
                </div>
              ))}
            </dl>
          </Panel>
        </div>
      </div>
    </>
  );
}
