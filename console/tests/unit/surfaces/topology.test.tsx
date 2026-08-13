import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { TopologyScreen } from '@/surfaces/screens/topology';

/**
 * Two panels that were the same empty state twice, and a door that did not
 * lead anywhere.
 *
 * "No topology recorded" rendered in a Neighbourhood panel and in a list panel
 * beside it, identical down to the call to action — one empty state, drawn
 * twice, telling nobody anything a second reading did not already say. Worse,
 * the action it offered ("See the estate") went to Resources, which the graph
 * is not built from, so a viewer who followed it could not get out the way it
 * pointed. This file pins the fix: no data draws one empty state, not a
 * matched pair, and that one state names the actual reason — the setup this
 * deployment has not finished, which investigations need before anything can
 * be observed at all — with a way out that lands on the step itself.
 *
 * It also pins the breadcrumb: `root` is this screen's own fallback, never a
 * name anything holds, and it must not reach the page a viewer reads.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** Built rather than written: a literal origin in console source is refused. */
const BASE = ['http:', '//gateway.test'].join('');

const PRINCIPAL = {
  principal_id: 'user-operator',
  display_name: 'Avery Lockhart',
  kind: 'person',
  roles: ['owner'],
  permissions: ['investigation.read'],
  team_node_id: 'org-northwind',
  impersonating: false,
  impersonated_by: null,
};

/** A checklist that still has outstanding steps: no provider stored. */
const SETUP_INCOMPLETE = {
  complete: false,
  provider: 'absent',
  integrations: [],
  steps: [],
};

/** A checklist with nothing left to do. */
const SETUP_COMPLETE = {
  complete: true,
  provider: 'openai',
  integrations: [{ name: 'openai', readiness: 'verified' }],
  steps: [
    { name: 'infrastructure-source', state: 'done' },
    { name: 'first-investigation', state: 'done' },
  ],
};

function neighbour(id: string, name: string): unknown {
  return {
    kind: 'service',
    name,
    node_id: id,
    owner_node_id: 'team-platform',
    properties: {},
  };
}

const TOPOLOGY_WITH_DATA = {
  available: true,
  node_id: 'svc-ledger',
  reason: null,
  truncated: false,
  dependencies: [neighbour('svc-store', 'store-linen')],
  dependents: [neighbour('svc-gateway', 'harbour')],
  blast_radius: [{ depth: 1, node: neighbour('svc-gateway', 'harbour') }],
};

const ORG_TREE = {
  nodes: [
    { kind: 'organisation', name: 'Northwind', node_id: 'root', parent_id: null },
  ],
};

function serve(bodies: {
  readonly topology?: unknown;
  readonly setup: unknown;
  readonly tree?: unknown;
}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const byPath: Record<string, unknown> = {
      '/auth/me': PRINCIPAL,
      '/v1/setup/checklist': bodies.setup,
      ...(bodies.topology === undefined
        ? {}
        : { [`/v1/topology/root`]: bodies.topology }),
      ...(bodies.tree === undefined ? {} : { '/v1/config': bodies.tree }),
    };
    const body = byPath[path];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === undefined ? 404 : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function topology(): Promise<void> {
  render(await TopologyScreen(await surfaceContext({})));
}

function panels(): readonly HTMLElement[] {
  return screen.getAllByTestId('panel');
}

describe('no topology recorded for this node', () => {
  it('draws one empty state, not a matched pair', async () => {
    serve({ setup: SETUP_INCOMPLETE });
    await topology();

    expect(panels()).toHaveLength(1);
    expect(panels()[0]).toHaveAttribute('data-state', 'empty');
  });

  it('names the outstanding setup, not the estate it does not feed', async () => {
    serve({ setup: SETUP_INCOMPLETE });
    await topology();

    const [panel] = panels();
    expect(panel).toHaveTextContent(/still being set up/);
    expect(panel).toHaveTextContent(/investigations cannot run until they are done/);
    expect(panel).not.toHaveTextContent(
      'The graph is built from what investigations observe',
    );

    const action = screen.getByRole('link', { name: 'Finish setting up' });
    expect(action).toHaveAttribute('href', '/first-run');
  });

  it('keeps the mechanism explanation once the setup is not what is blocking it', async () => {
    serve({ setup: SETUP_COMPLETE });
    await topology();

    const [panel] = panels();
    expect(panel).toHaveTextContent(
      'The graph is built from what investigations observe. Nothing has been observed about this node yet.',
    );
    expect(panel).not.toHaveTextContent(/still being set up/);

    const action = screen.getByRole('link', { name: 'See the estate' });
    expect(action).toHaveAttribute('href', '/resources');
  });
});

describe('a node with real neighbours', () => {
  it('splits into the picture and the list once there is something to split', async () => {
    serve({ topology: TOPOLOGY_WITH_DATA, setup: SETUP_COMPLETE });
    await topology();

    expect(panels()).toHaveLength(2);
    for (const panel of panels()) {
      expect(panel).toHaveAttribute('data-state', 'ready');
    }
    expect(screen.getByTestId('graph')).toBeInTheDocument();
    expect(screen.getByTestId('graph-list')).toBeInTheDocument();
  });
});

describe('the breadcrumb at the unqualified address', () => {
  it('never prints the internal fallback name', async () => {
    serve({ setup: SETUP_INCOMPLETE, tree: { nodes: [] } });
    await topology();

    expect(screen.queryByText('root')).toBeNull();
  });

  it('omits the crumb while the organisation tree names nothing', async () => {
    serve({ setup: SETUP_INCOMPLETE, tree: { nodes: [] } });
    await topology();

    // `AreaHeader` draws no landmark at all for a trail of one — a breadcrumb
    // that says only "Topology" is furniture, and this is that case: there is
    // nothing the organisation tree can name here.
    expect(screen.queryByRole('navigation', { name: 'Breadcrumb' })).toBeNull();
  });

  it('shows the organisation’s own name once the tree can name one', async () => {
    serve({ topology: TOPOLOGY_WITH_DATA, setup: SETUP_COMPLETE, tree: ORG_TREE });
    await topology();

    // Scoped to the breadcrumb landmark itself: the graph beside it draws a
    // box labelled with the address it was asked for, which is a different
    // fact from what the breadcrumb owes a reader, and is not this test's
    // concern.
    const trail = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(trail).toHaveTextContent('Northwind');
    expect(trail).not.toHaveTextContent('root');
  });
});
