import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { formatNumber } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { emptyBecause, readSetupState, setupCause } from '../emptiness';
import { DependencyGraph, NEIGHBOUR_BOUND, type GraphNode } from '../graph';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  list,
  number,
  optionalRead,
  read,
  stateOf,
  text,
} from '../read';
import { placedTree } from '../tree';
import { readViewState, type FilterName } from '../url-state';

/**
 * How the estate is connected, as the platform understands it.
 *
 * Two views of one graph — a picture for a glance and a list for a keyboard, a
 * screen reader, and the two hundred dependents the picture is bounded away
 * from drawing — but only once there is a graph to show two views of. An empty
 * neighbourhood and an empty list are the same fact stated twice, so this
 * renders one empty state, not a matched pair, and only splits into the
 * picture and the list once there is something to split.
 *
 * The empty state itself names the reason *this* deployment has nothing here:
 * the graph is built from what investigations observe, and an unfinished setup
 * means no investigation has run at all. Pointing at Resources — a screen the
 * graph is not fed by — was a door that did not lead anywhere; `setupCause`
 * closes the chain instead.
 */

export const TOPOLOGY_FILTERS: readonly FilterName[] = ['node'];

/** Which node the graph is centred on when the address does not say. */
const DEFAULT_NODE = 'root';

function nodesFrom(records: readonly unknown[]): readonly GraphNode[] {
  return records.map((record) => ({
    id: text(record, 'node_id'),
    name: text(record, 'name') === '' ? text(record, 'node_id') : text(record, 'name'),
    kind: text(record, 'kind'),
    href: `/topology?node=${encodeURIComponent(text(record, 'node_id'))}`,
  }));
}

export async function TopologyScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, search } = context;
  const state = readViewState(search, TOPOLOGY_FILTERS);
  const nodeId = state.filters.node ?? DEFAULT_NODE;
  // `root` is a sentinel this screen falls back to, not a node any tree names
  // — so it is never fit to print. The organisation's own name is what the
  // breadcrumb owes a viewer standing at the unqualified address.
  const atRoot = nodeId === DEFAULT_NODE;
  const init = authorised(credential);

  const [topology, setup, tree] = await Promise.all([
    // A node nothing has observed yet answers 404 — the ordinary state of a
    // deployment whose investigations have not run, not a failure — so this
    // reads the way `/v1/config/{node_id}` does: a 404 here is data, and only
    // a refused or unreachable gateway is this panel's error.
    optionalRead('/v1/topology/{node_id}', () =>
      read('/v1/topology/{node_id}', { ...init, params: { node_id: nodeId } }),
    ),
    readSetupState(credential),
    // Read for the breadcrumb alone, and only worth the name at the root: a
    // node reached through `?node=` already carries a real name in the graph
    // it came from, and asking the organisation tree about it would be asking
    // the wrong document.
    optionalRead('/v1/config', () => read('/v1/config', init)),
  ]);

  const body = dataOf(topology);
  const dependencies = nodesFrom(list(body, 'dependencies'));
  const dependents = nodesFrom(list(body, 'dependents'));
  const blast = list(body, 'blast_radius');
  const empty = dependencies.length === 0 && dependents.length === 0;
  const resolvedState = stateOf(topology, empty);

  const subject: GraphNode = {
    id: nodeId,
    name: nodeId,
    kind: '',
    href: `/topology?node=${encodeURIComponent(nodeId)}`,
  };

  const bounded = Math.max(dependencies.length, dependents.length) > NEIGHBOUR_BOUND;

  // Investigations feed the graph and cannot run before the setup they need
  // is finished, so an unfinished checklist — not "nothing has been observed
  // yet" — is why this deployment's neighbourhood is blank.
  const cause = setupCause(locale, setup);
  const emptyState = emptyBecause(
    {
      heading: message(locale, 'topology.empty.heading'),
      body: message(locale, 'topology.empty.body'),
      actionLabel: message(locale, 'topology.empty.action'),
      href: '/resources',
    },
    cause,
  );

  const orgName = atRoot ? (placedTree(dataOf(tree))[0]?.name ?? '') : '';
  const nested = atRoot
    ? orgName === ''
      ? []
      : [{ label: orgName }]
    : [{ label: nodeId }];

  return (
    <>
      <AreaHeader area={areaFor('topology')} locale={locale} nested={nested} />

      {resolvedState === 'empty' ? (
        <Panel
          title={message(locale, 'topology.graph.title')}
          state={resolvedState}
          dependency={dependencyOf(topology)}
          labels={panelLabels(locale, message(locale, 'topology.graph.title'))}
          empty={emptyState}
        />
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="lg:col-span-2 min-w-0">
            <Panel
              title={message(locale, 'topology.graph.title')}
              state={resolvedState}
              dependency={dependencyOf(topology)}
              labels={panelLabels(locale, message(locale, 'topology.graph.title'))}
              empty={emptyState}
            >
              <DependencyGraph
                subject={subject}
                dependencies={dependencies}
                dependents={dependents}
                labels={{
                  title: message(locale, 'topology.graph.title'),
                  dependencies: message(locale, 'topology.dependencies'),
                  dependents: message(locale, 'topology.dependents'),
                }}
              />
              {bounded ? (
                <p data-testid="graph-bound" className="text-meta text-muted mt-2">
                  {message(locale, 'topology.bounded', {
                    shown: formatNumber(locale, NEIGHBOUR_BOUND),
                    total: formatNumber(
                      locale,
                      Math.max(dependencies.length, dependents.length),
                    ),
                  })}
                </p>
              ) : null}
            </Panel>
          </div>

          <div className="min-w-0">
            <Panel
              title={message(locale, 'topology.list.title')}
              state={resolvedState}
              dependency={dependencyOf(topology)}
              labels={panelLabels(locale, message(locale, 'topology.list.title'))}
              empty={emptyState}
            >
              {/* Every neighbour, not the bounded set. This is the complete view;
                  the picture is the readable one. */}
              <div data-testid="graph-list" className="flex flex-col gap-4 text-small">
                <section>
                  <h4 className="text-strong mb-1">
                    {message(locale, 'topology.dependencies')}
                  </h4>
                  <ul className="flex flex-col gap-1">
                    {dependencies.map((node) => (
                      <li key={node.id} className="min-w-0 truncate">
                        <Link href={node.href}>{node.name}</Link>
                      </li>
                    ))}
                  </ul>
                </section>
                <section>
                  <h4 className="text-strong mb-1">
                    {message(locale, 'topology.dependents')}
                  </h4>
                  <ul className="flex flex-col gap-1">
                    {dependents.map((node) => (
                      <li key={node.id} className="min-w-0 truncate">
                        <Link href={node.href}>{node.name}</Link>
                      </li>
                    ))}
                  </ul>
                </section>
                <section>
                  <h4 className="text-strong mb-1">
                    {message(locale, 'topology.blast')}
                  </h4>
                  <ul className="flex flex-col gap-1">
                    {blast.map((entry) => {
                      const node = field(entry, 'node');
                      return (
                        <li
                          key={text(node, 'node_id')}
                          data-testid="blast-entry"
                          className="flex items-center gap-2 min-w-0"
                        >
                          <span className="truncate">{text(node, 'name')}</span>
                          <span className="ml-auto text-meta text-muted">
                            {message(locale, 'topology.depth', {
                              depth: formatNumber(locale, number(entry, 'depth')),
                            })}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              </div>
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}
