import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { serveScenario } from '../support/dataset';

/**
 * The autonomy screen's own defects, on top of what `screens.test.tsx` already
 * proves for every screen.
 *
 * Three things this file exists to catch that the cross-cutting suite cannot,
 * because they are about *this* screen's shape rather than every screen's:
 *
 * - reading no rules and reading no bounds used to be reported by three panels
 *   in the same words, and a reader could not tell three repeats of "nothing"
 *   from one; now it is one panel, and the editor that would create the first
 *   rule sits directly beneath it, already carrying one row to choose a level
 *   for and save — never a bare link to a different screen;
 * - the bounds panel drops out of the page only when it would otherwise repeat
 *   that same "nothing recorded", never when it holds real content or is
 *   itself failing to load;
 * - the stopped row carries the same control the topbar does, so resuming
 *   automation is available on the screen that governs what automation may
 *   do, and only for a viewer who may use it.
 */

const BASE = ['http:', '//fixtures.invalid'].join('');

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === 'ninjasre_session' ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderAutonomy(
  query: Readonly<Record<string, string>> = {},
): Promise<void> {
  const { default: Page } = await import('@/app/(shell)/autonomy/page');
  render(await Page({ searchParams: Promise.resolve(query) }));
}

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const NODE = 'org-northwind';

const SINGLE_NODE = {
  kind: 'organisation',
  name: 'Northwind',
  node_id: NODE,
  parent_id: null,
};

const WRITER = {
  principal_id: 'user-operator',
  display_name: 'Avery Lockhart',
  email: 'avery.lockhart@example.invalid',
  kind: 'person',
  roles: ['owner'],
  permissions: ['config.read', 'config.write', 'remediation.execute'],
  team_node_id: NODE,
  impersonated_by: null,
  impersonating: false,
};

const READER = {
  ...WRITER,
  principal_id: 'user-viewer',
  display_name: 'Reese Underhill',
  permissions: ['config.read'],
};

const EMPTY_BOUNDS = {
  node_id: NODE,
  stopped: false,
  stop_reason: '',
  freezes: [],
  budgets: [],
  overrides: [],
  expired_overrides: [],
};

const EMPTY_POLICY = {
  node_id: NODE,
  dry_run: false,
  rules: [],
};

interface Stub {
  readonly tree?: readonly unknown[];
  readonly principal?: unknown;
  readonly policy?: unknown;
  readonly bounds?: unknown;
}

/** One deployment, one node, and whatever policy and bounds this test needs. */
function serveAutonomy({
  tree = [SINGLE_NODE],
  principal = WRITER,
  policy,
  bounds,
}: Stub): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/auth/me') return Promise.resolve(respond(principal));
    if (path === '/v1/config') return Promise.resolve(respond({ nodes: tree }));
    if (path === `/v1/autonomy/policy/${NODE}`) {
      return policy === undefined
        ? Promise.resolve(respond({}, 404))
        : Promise.resolve(respond(policy));
    }
    if (path === `/v1/autonomy/policy/${NODE}/bounds`) {
      return bounds === undefined
        ? Promise.resolve(respond({}, 404))
        : Promise.resolve(respond(bounds));
    }
    return Promise.resolve(respond({}, 404));
  });
}

function emptyPanels(): HTMLElement[] {
  return screen
    .getAllByTestId('panel')
    .filter((panel) => panel.getAttribute('data-state') === 'empty');
}

describe('a node with no rule and no bound recorded', () => {
  it('shows exactly one empty panel, with the first-rule editor directly beneath it', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy();

    expect(emptyPanels()).toHaveLength(1);

    // The bounds panel, which would otherwise repeat the same "nothing
    // recorded", is not on the page at all.
    expect(
      screen.queryByRole('heading', { name: 'Bounds and level overrides' }),
    ).not.toBeInTheDocument();

    // The editor a real rule would use is here, already, seeded with one
    // deployment-wide row rather than an empty list.
    const editor = screen.getByTestId('autonomy-editor');
    const seeded = screen.getByTestId('rule-editor');
    expect(seeded.getAttribute('data-rule')).toBe('deployment');
    expect(editor).toBeInTheDocument();
  });

  it('leaves the editor and the override panel out for a viewer who may not write', async () => {
    serveAutonomy({ principal: READER, policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy();

    expect(emptyPanels()).toHaveLength(1);
    expect(screen.queryByTestId('autonomy-editor')).not.toBeInTheDocument();
    expect(screen.queryByTestId('override-editor')).not.toBeInTheDocument();
  });
});

describe('a deployment with no organisation tree at all', () => {
  it('shows exactly one empty panel and nothing that needs a node', async () => {
    serveAutonomy({
      tree: [],
      principal: { ...WRITER, team_node_id: '' },
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy();

    expect(emptyPanels()).toHaveLength(1);
    expect(screen.queryByTestId('autonomy-editor')).not.toBeInTheDocument();
    expect(screen.queryByTestId('override-editor')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Bounds and level overrides' }),
    ).not.toBeInTheDocument();
  });
});

describe('no rule recorded, but a freeze window is', () => {
  it('still shows only one empty panel, and the bounds panel keeps its real content', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: {
        ...EMPTY_BOUNDS,
        freezes: [
          {
            name: 'nightly-backups',
            start: '01:00',
            end: '04:00',
            timezone: 'Europe/Lisbon',
            reason: 'backups run',
            scope: { kind: 'deployment' },
          },
        ],
      },
    });

    await renderAutonomy();

    expect(emptyPanels()).toHaveLength(1);
    expect(
      screen.getByRole('heading', { name: 'Bounds and level overrides' }),
    ).toBeInTheDocument();
    expect(screen.getByText('nightly-backups')).toBeInTheDocument();
  });
});

describe('automated writes are stopped', () => {
  it('names why, and offers the same control the topbar carries, to a viewer who may use it', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: {
        ...EMPTY_BOUNDS,
        stopped: true,
        stop_reason:
          'Automated writes are stopped for this organisation, engaged by user-operator',
      },
    });

    await renderAutonomy();

    const stoppedRow = screen.getByTestId('autonomy-stopped');
    expect(stoppedRow).toHaveTextContent(
      'Automated writes are stopped for this organisation, engaged by user-operator',
    );
    expect(screen.getByTestId('release-stop')).toBeInTheDocument();
  });

  it('names why, without offering the control, to a viewer who may not use it', async () => {
    serveAutonomy({
      principal: READER,
      policy: EMPTY_POLICY,
      bounds: {
        ...EMPTY_BOUNDS,
        stopped: true,
        stop_reason: 'Automated writes are stopped for this organisation',
      },
    });

    await renderAutonomy();

    expect(screen.getByTestId('autonomy-stopped')).toHaveTextContent(
      'Automated writes are stopped for this organisation',
    );
    expect(screen.queryByTestId('release-stop')).not.toBeInTheDocument();
    expect(screen.queryByTestId('engage-stop')).not.toBeInTheDocument();
  });
});

describe('a populated node', () => {
  it('renders nothing as empty', async () => {
    serveScenario('populated');

    await renderAutonomy();

    expect(emptyPanels()).toHaveLength(0);
    expect(
      screen.getByRole('heading', { name: 'Bounds and level overrides' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('autonomy-footer')).toBeInTheDocument();
  });
});
