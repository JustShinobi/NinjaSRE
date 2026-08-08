import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { formatNumber } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
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
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { readViewState, type FilterName } from '../url-state';

/**
 * How the estate is connected, as the platform understands it.
 *
 * Two views of one graph, and both are always there. The picture is what a
 * person reads at a glance; the list is what a keyboard walks, what a screen
 * reader announces, and what holds the two hundred dependents the picture is
 * bounded away from drawing. Calling the list a fallback would be wrong — it is
 * the complete one.
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

  const topology = await panelRead('/v1/topology/{node_id}', () =>
    read('/v1/topology/{node_id}', {
      ...authorised(credential),
      params: { node_id: nodeId },
    }),
  );

  const body = dataOf(topology);
  const dependencies = nodesFrom(list(body, 'dependencies'));
  const dependents = nodesFrom(list(body, 'dependents'));
  const blast = list(body, 'blast_radius');
  const empty = dependencies.length === 0 && dependents.length === 0;

  const subject: GraphNode = {
    id: nodeId,
    name: nodeId,
    kind: '',
    href: `/topology?node=${encodeURIComponent(nodeId)}`,
  };

  const bounded = Math.max(dependencies.length, dependents.length) > NEIGHBOUR_BOUND;

  return (
    <>
      <AreaHeader
        area={areaFor('topology')}
        locale={locale}
        nested={[{ label: nodeId }]}
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0">
          <Panel
            title={message(locale, 'topology.graph.title')}
            state={stateOf(topology, empty)}
            dependency={dependencyOf(topology)}
            labels={panelLabels(locale, message(locale, 'topology.graph.title'))}
            empty={{
              heading: message(locale, 'topology.empty.heading'),
              body: message(locale, 'topology.empty.body'),
              actionLabel: message(locale, 'topology.empty.action'),
              href: '/resources',
            }}
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
            state={stateOf(topology, empty)}
            dependency={dependencyOf(topology)}
            labels={panelLabels(locale, message(locale, 'topology.list.title'))}
            empty={{
              heading: message(locale, 'topology.empty.heading'),
              body: message(locale, 'topology.empty.body'),
              actionLabel: message(locale, 'topology.empty.action'),
              href: '/resources',
            }}
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
    </>
  );
}
