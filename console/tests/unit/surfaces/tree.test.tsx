import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  OrgNav,
  OrgTree,
  placeNodes,
  placedTree,
  type TreeNode,
} from '@/surfaces/tree';

/**
 * Five hundred configuration nodes, every one of them present.
 *
 * "Every one" is the assertion that costs something: a tree that collapsed the
 * deep ones would render instantly and would be a tree an operator cannot find
 * their own team in. So the budget below is held *together with* a count, and
 * the count is the one that would fail first if somebody made this fast by
 * showing less.
 */

function budget(name: string): number {
  const source = readFileSync(
    join(process.cwd(), '..', 'config', 'constants', 'console.py'),
    'utf8',
  );
  const found = new RegExp(`^${name}: Final = ([0-9.]+)`, 'm').exec(source);
  if (found?.[1] === undefined) {
    throw new Error(`${name} is not declared in config/constants/console.py`);
  }
  return Number(found[1]);
}

const TREE_BUDGET_MS = budget('CONSOLE_CONFIG_TREE_RENDER_BUDGET_MS');

/** `count` nodes, ten deep, so the depth walk has something to walk. */
function organisation(count: number): readonly TreeNode[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `node-${String(index)}`,
    name: `team ${String(index)}`,
    kind: index === 0 ? 'org' : 'team',
    parentId: index === 0 ? null : `node-${String(Math.floor((index - 1) / 3))}`,
  }));
}

describe('placing a flat list as a tree', () => {
  it('gives each node the depth of its parent chain', () => {
    // Depth-first, so the order is the order a reader's eye goes down the tree
    // rather than the order the API happened to send.
    const placed = placeNodes(organisation(5));

    expect(placed.map((node) => node.depth)).toEqual([0, 1, 2, 1, 1]);
  });

  it('keeps a node whose parent is missing rather than dropping it', () => {
    // A partial tree is a fact about the data. A node that vanished is a fact
    // about the renderer, and only one of those is actionable.
    const placed = placeNodes([
      { id: 'a', name: 'a', kind: 'team', parentId: 'nowhere' },
    ]);

    expect(placed).toHaveLength(1);
    expect(placed[0]?.depth).toBe(0);
  });

  it('terminates on a parent chain that points at itself', () => {
    const placed = placeNodes([
      { id: 'a', name: 'a', kind: 'team', parentId: 'b' },
      { id: 'b', name: 'b', kind: 'team', parentId: 'a' },
    ]);

    expect(placed.map((node) => node.id).sort()).toEqual(['a', 'b']);
  });

  it('reads in tree order rather than in the order the API sent', () => {
    const placed = placeNodes(organisation(5));

    expect(placed[0]?.id).toBe('node-0');
    expect(placed[1]?.id).toBe('node-1');
    expect(placed[2]?.id).toBe('node-4');
  });
});

describe('SC-008: five hundred nodes', () => {
  it('are all present, and render inside the declared budget', () => {
    const nodes = placeNodes(organisation(500));

    const started = performance.now();
    render(
      <OrgTree
        nodes={nodes}
        selected="node-3"
        label="Organisation"
        hrefFor={(id) => `/configuration?node=${id}`}
      />,
    );
    const spent = performance.now() - started;

    // The count first: a tree made fast by drawing less would fail here rather
    // than pass the stopwatch.
    expect(screen.getAllByTestId('org-node')).toHaveLength(500);
    expect(screen.getByTestId('org-tree')).toHaveAttribute('data-total', '500');
    expect(spent, `five hundred nodes took ${spent.toFixed(0)}ms`).toBeLessThan(
      TREE_BUDGET_MS,
    );
  });

  it('marks the selected node, and only that one', () => {
    render(
      <OrgTree
        nodes={placeNodes(organisation(9))}
        selected="node-3"
        label="Organisation"
        hrefFor={(id) => `/configuration?node=${id}`}
      />,
    );

    const current = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current') === 'true');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute('href', '/configuration?node=node-3');
  });
});

/**
 * The Organisation panel's own body: the tree, or the breadcrumb that
 * replaces it once there is nothing to navigate.
 *
 * Every screen that shows this panel — Team context and Configuration today
 * — read this same two-branch decision, each keeping its own copy of it,
 * until both were moved onto this one function. The two branches were
 * already characterised, screen by screen: `team-context.test.tsx`'s two
 * tests and `configuration-tree.test.tsx`'s two tests exercise the same
 * logic through each screen's own render and continue to pass unchanged
 * after this extraction. These two are the direct, isolated tests of the
 * shared function itself.
 */
describe('the organisation panel: a tree, or a breadcrumb with nothing to navigate', () => {
  it('draws the tree once there is more than one node', () => {
    render(
      <OrgNav
        nodes={placeNodes(organisation(3))}
        selected="node-0"
        label="Organisation"
        hrefFor={(id) => `/configuration?node=${id}`}
      />,
    );

    expect(screen.getByTestId('org-tree')).toBeInTheDocument();
    expect(screen.queryByTestId('org-breadcrumb')).not.toBeInTheDocument();
  });

  it('collapses to a breadcrumb naming the one node, rather than a one-row nav', () => {
    render(
      <OrgNav
        nodes={placeNodes([
          {
            id: 'org-northwind',
            name: 'Northwind',
            kind: 'organisation',
            parentId: null,
          },
        ])}
        selected="org-northwind"
        label="Organisation"
        hrefFor={(id) => `/configuration?node=${id}`}
      />,
    );

    expect(screen.getByTestId('org-breadcrumb')).toHaveTextContent('Northwind');
    expect(screen.queryByTestId('org-tree')).not.toBeInTheDocument();
  });
});

/**
 * The tree, read out of the payload the gateway sends.
 *
 * Three screens need the organisation before they can name a node, and each of
 * them was reading `nodes`, `node_id`, `parent_id` out of an `unknown` by hand.
 * One reader, so a field that is renamed is renamed once.
 */
describe('the tree a config payload describes', () => {
  it('places the nodes it carries, root first', () => {
    const placed = placedTree({
      nodes: [
        { node_id: 'team-platform', name: 'Platform', kind: 'team', parent_id: 'org' },
        { node_id: 'org', name: 'Northwind', kind: 'organisation', parent_id: null },
      ],
    });

    expect(placed.map((node) => node.id)).toEqual(['org', 'team-platform']);
    expect(placed.map((node) => node.depth)).toEqual([0, 1]);
  });

  it('is empty for a payload that carries nothing, rather than a throw', () => {
    // What a deployment nobody has configured answers, and what a failed read
    // hands on: neither is a defect, and neither may take a page down.
    expect(placedTree({ nodes: [] })).toEqual([]);
    expect(placedTree(undefined)).toEqual([]);
  });
});
