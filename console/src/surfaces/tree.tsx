import type { ReactNode } from 'react';

import { dataOf, list, optionalRead, read, text } from './read';

/**
 * The organisation, as a tree, in one pass over a flat list.
 *
 * Depth is computed by walking each node's parent chain through a map rather
 * than by rendering recursively, and that is what lets five hundred nodes all be
 * present: a recursive render of a deep tree is a stack of components per level
 * and a re-render of a whole subtree whenever one node's selection changes.
 *
 * Every node is drawn. A tree that collapsed the deep ones would be a tree an
 * operator cannot find their own team in, and "find your team" is the only thing
 * anybody opens this for.
 */

/** One node, as the API sends it. */
export interface TreeNode {
  readonly id: string;
  readonly name: string;
  readonly kind: string;
  readonly parentId: string | null;
}

/** A node with its depth and its address, ready to draw. */
export interface PlacedNode extends TreeNode {
  readonly depth: number;
}

/** How deep the walk goes before it decides the parent chain is a cycle. */
const DEPTH_BOUND = 64;

/**
 * `nodes` in the order a tree reads, each with its depth.
 *
 * A node whose parent is missing is placed at the root rather than dropped. A
 * partial tree is a fact about the data; a node that vanished is a fact about
 * the renderer, and only one of those is something an operator can act on.
 */
export function placeNodes(nodes: readonly TreeNode[]): readonly PlacedNode[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));

  function depthOf(node: TreeNode): number {
    let depth = 0;
    let current = node;
    while (current.parentId !== null && depth < DEPTH_BOUND) {
      const parent = byId.get(current.parentId);
      if (parent === undefined) break;
      current = parent;
      depth += 1;
    }
    return depth;
  }

  const children = new Map<string, TreeNode[]>();
  const roots: TreeNode[] = [];
  for (const node of nodes) {
    const parent = node.parentId === null ? undefined : byId.get(node.parentId);
    if (parent === undefined) {
      roots.push(node);
    } else {
      const held = children.get(parent.id) ?? [];
      held.push(node);
      children.set(parent.id, held);
    }
  }

  const placed: PlacedNode[] = [];
  const stack = [...roots].reverse();
  const seen = new Set<string>();
  while (stack.length > 0) {
    const node = stack.pop();
    if (node === undefined || seen.has(node.id)) continue;
    seen.add(node.id);
    placed.push({ ...node, depth: depthOf(node) });
    const own = children.get(node.id) ?? [];
    for (let index = own.length - 1; index >= 0; index -= 1) {
      const child = own[index];
      if (child !== undefined) stack.push(child);
    }
  }

  // Anything the walk could not reach — a cycle in the parent chain is the only
  // way — is appended at the root rather than dropped. A malformed tree is a
  // thing an operator can go and fix; a node that silently vanished is a thing
  // they conclude the console cannot show.
  for (const node of nodes) {
    if (!seen.has(node.id)) {
      placed.push({ ...node, depth: 0 });
    }
  }
  return placed;
}

/**
 * The organisation a `/v1/config` payload describes, placed and ready to draw.
 *
 * Every screen that is scoped to a node needs the tree before it can name one,
 * and each of them was picking `nodes`, `node_id` and `parent_id` out of an
 * `unknown` in its own words. One reader, so a field the API renames is renamed
 * here and nowhere else.
 *
 * A payload that carries nothing — an unconfigured deployment, or a read that
 * failed and handed on `undefined` — is an empty tree rather than a throw. That
 * is the whole point of it being one function: the emptiness is answered once,
 * in the place that knows what the shape is.
 */
export function placedTree(payload: unknown): readonly PlacedNode[] {
  return placeNodes(
    list(payload, 'nodes').map((record) => ({
      id: text(record, 'node_id'),
      name: text(record, 'name'),
      kind: text(record, 'kind'),
      parentId: text(record, 'parent_id') === '' ? null : text(record, 'parent_id'),
    })),
  );
}

/**
 * The node a viewer's configuration writes land at: their own team, or — when
 * the session names none — the root of the tree they may see.
 *
 * The second half is the same fallback the configuration screen applies when
 * nothing has chosen a node yet, made reachable for screens that have no tree
 * of their own on the page. It costs a read only on the sessions that need it.
 * A viewer with no team and no visible tree resolves to the empty string, and
 * a caller holding that writes nothing.
 */
export async function viewerNode(
  viewer: { readonly teamNodeId: string },
  init: RequestInit,
): Promise<string> {
  if (viewer.teamNodeId !== '') return viewer.teamNodeId;
  const tree = await optionalRead('/v1/config', () => read('/v1/config', init));
  return placedTree(dataOf(tree))[0]?.id ?? '';
}

export interface OrgTreeProps {
  readonly nodes: readonly PlacedNode[];
  readonly selected: string;
  /** Where a node goes when it is chosen. Built by the screen, so it is a link. */
  readonly hrefFor: (id: string) => string;
  readonly label: string;
}

/** The tree, every node of it, as a list of links. */
export function OrgTree({ nodes, selected, hrefFor, label }: OrgTreeProps): ReactNode {
  return (
    <nav aria-label={label}>
      <ul data-testid="org-tree" data-total={nodes.length} className="flex flex-col">
        {nodes.map((node) => (
          <li key={node.id} data-testid="org-node" data-node={node.id}>
            <a
              href={hrefFor(node.id)}
              aria-current={node.id === selected ? 'true' : undefined}
              data-selected={node.id === selected}
              className={
                node.id === selected
                  ? 'flex items-center gap-2 px-2 py-1 rounded-2 bg-accent-bg text-accent text-small'
                  : 'flex items-center gap-2 px-2 py-1 rounded-2 text-small motion-hover hover:bg-hover'
              }
              // Indentation is a drawing measurement rather than a spacing step:
              // it multiplies with depth, and a scale step that multiplied would
              // stop being a step.
              style={{ marginInlineStart: `${String(node.depth * 12)}px` }}
            >
              <span className="truncate">{node.name}</span>
              <span className="ml-auto text-meta text-muted">{node.kind}</span>
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
