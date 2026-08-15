import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { surfaceContext } from '@/surfaces/context';
import { AutonomyScreen } from '@/surfaces/settings/autonomy';

import { serveScenario } from '../../support/dataset';

/**
 * The Autonomy & guardrails page's own defects, on top of what
 * `screens.test.tsx` already proves for every screen.
 *
 * Migrated from `console/src/surfaces/screens/autonomy.tsx`, which this page
 * absorbed whole: the properties below are the ones that screen already held
 * and this file continues to hold them against the new component, so
 * rebuilding the screen at its Settings address never quietly drops one.
 *
 * Four things this file exists to catch that the cross-cutting suite cannot,
 * because they are about *this* page's shape rather than every screen's:
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
 *   do, and only for a viewer who may use it;
 * - no empty state anywhere on this page links to the raw configuration
 *   editor — see `console/tests/unit/surfaces/autonomy-editor.test.tsx` for
 *   the rule/freeze/budget creation this loop was replaced with.
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
  // The page itself, not `/autonomy`'s own route file: that address now
  // redirects to `/settings/autonomy-guardrails`, which renders this same
  // page — `console/tests/unit/shell/route-files.test.tsx` covers the
  // redirect, and this file is about the page's own content.
  render(await AutonomyScreen(await surfaceContext(query)));
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
  readonly values?: unknown;
  readonly provenance?: Readonly<Record<string, string>>;
  readonly fields?: readonly unknown[];
}

/** One deployment, one node, and whatever policy and bounds this test needs. */
function serveAutonomy({
  tree = [SINGLE_NODE],
  principal = WRITER,
  policy,
  bounds,
  values,
  provenance = {},
  fields = [],
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
    if (path === `/v1/config/${NODE}`) {
      return values === undefined
        ? Promise.resolve(respond({}, 404))
        : Promise.resolve(respond({ node_id: NODE, values, provenance }));
    }
    if (path === `/v1/config/${NODE}/fields`) {
      return Promise.resolve(respond({ fields }));
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

describe('the vocabulary this screen assumes an operator already has', () => {
  it('defines a rule, a bound and an override in the reader’s own words, near the top of the page', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy();

    const glossary = screen.getByTestId('autonomy-glossary');
    expect(glossary).toHaveTextContent(/rule/i);
    expect(glossary).toHaveTextContent(/bound/i);
    expect(glossary).toHaveTextContent(/override/i);
  });
});

describe('an active override on the bounds this node holds', () => {
  it('is shown to a writer with its own revoke button, never a name typed from memory', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: {
        ...EMPTY_BOUNDS,
        overrides: [
          {
            name: 'incident-widen',
            scope: { kind: 'deployment' },
            level: 'act_and_report',
            risk_bound: 'low',
            expires_at: '2026-08-14T00:00:00Z',
            granted_by: 'user-operator',
            reason: 'restoring a paged service',
          },
        ],
      },
    });

    await renderAutonomy();

    expect(screen.queryByTestId('override-revoke-empty')).not.toBeInTheDocument();
    // Specifically the row *inside the revoke section*, not the read-only
    // mention of the same override in the bounds panel above it — a test that
    // only checked for the name anywhere on the page would pass against the
    // unmodified free-text control too, since that name is already shown
    // there.
    const row = screen.getByTestId('active-override');
    expect(row).toHaveTextContent('incident-widen');
    expect(screen.getByTestId('revoke-override')).toBeInTheDocument();
  });

  it('says there is nothing to revoke for a node with none active', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy();

    expect(screen.queryByTestId('revoke-override')).not.toBeInTheDocument();
    expect(screen.getByTestId('override-revoke-empty')).toBeInTheDocument();
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

describe('the rules table, over every scope kind the deployment may send', () => {
  it('reads the matching field for a team, a resource kind, labels, a capability, and a resource', async () => {
    serveAutonomy({
      policy: {
        ...EMPTY_POLICY,
        rules: [
          {
            rule_id: 'r1',
            scope: { kind: 'team', team_node_id: 'team-payments' },
            level: 'propose_only',
          },
          {
            rule_id: 'r2',
            scope: { kind: 'resource_kind', resource_kind: 'vm' },
            level: 'propose_only',
          },
          {
            rule_id: 'r3',
            scope: { kind: 'labels', labels: { tier: 'critical', region: 'eu' } },
            level: 'propose_only',
          },
          {
            rule_id: 'r4',
            scope: { kind: 'capability', capability: 'estate.restart' },
            level: 'act_and_report',
          },
          {
            rule_id: 'r5',
            scope: { kind: 'resource', resource_id: 'vm-9' },
            level: 'propose_only',
          },
          {
            rule_id: 'r6',
            scope: {
              kind: 'capability_resource',
              capability: 'estate.restart',
              resource_id: 'vm-9',
            },
            level: 'act_on_low_risk',
            risk_bound: 'low',
          },
        ],
      },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy();

    const rows = screen.getAllByTestId('autonomy-rule');
    expect(rows).toHaveLength(6);
    expect(rows[0]).toHaveTextContent('team-payments');
    expect(rows[1]).toHaveTextContent('vm');
    expect(rows[2]).toHaveTextContent('region=eu, tier=critical');
    expect(rows[3]).toHaveTextContent('estate.restart');
    expect(rows[4]).toHaveTextContent('vm-9');
    expect(rows[5]).toHaveTextContent('estate.restart on vm-9');
    // The risk bound column shows a value only for `act_on_low_risk`.
    expect(rows[5]).toHaveTextContent('low');
    expect(rows[3]).toHaveTextContent('—');
  });
});

describe('the guardrails section', () => {
  it('shows masking, guardrail and approval fields with their effective value and origin', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: {
        policies: {
          masking: { enabled: true, level: 'strict' },
          guardrails: { mode: 'enforcing', ruleset: null },
          approvals: { threshold: 'write_reversible', expiry_hours: 4.5 },
        },
      },
      provenance: { 'policies.masking.enabled': NODE },
      fields: [
        {
          path: 'policies.masking.enabled',
          label: 'Masking enabled',
          type: 'boolean',
          section: 'Masking',
          value: true,
          provenance: NODE,
          set_here: true,
        },
      ],
    });

    await renderAutonomy();

    function rowFor(path: string): HTMLElement {
      const row = screen
        .getAllByTestId('effective-field')
        .find((each) => each.getAttribute('data-path') === path);
      if (row === undefined) throw new Error(`no effective-field row for ${path}`);
      return row;
    }

    expect(rowFor('policies.masking.enabled')).toHaveTextContent('true');
    expect(rowFor('policies.masking.level')).toHaveTextContent('strict');
    expect(rowFor('policies.guardrails.mode')).toHaveTextContent('enforcing');
    // `ruleset` is unset (`null`) — the row still exists, naming the field, with
    // no value cell text of its own.
    expect(rowFor('policies.guardrails.ruleset')).toBeInTheDocument();
    expect(rowFor('policies.approvals.threshold')).toHaveTextContent(
      'write_reversible',
    );
    expect(rowFor('policies.approvals.expiry_hours')).toHaveTextContent('4.5');
    // The two constitutional invariants are stated as facts, never as a toggle.
    const invariants = screen.getAllByTestId('guardrail-invariant');
    expect(invariants).toHaveLength(2);
    expect(screen.getByTestId('config-editor')).toBeInTheDocument();
  });

  it('leaves the editor out, keeping the read-only rows, for a viewer who may not write', async () => {
    serveAutonomy({
      principal: READER,
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: { policies: { masking: { enabled: false, level: 'standard' } } },
    });

    await renderAutonomy();

    expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('effective-field').length).toBeGreaterThan(0);
  });
});

describe('the loop into the raw editor', () => {
  it('sends no empty state, on an empty node, to /configuration', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy();

    for (const link of screen.getAllByTestId('way-back')) {
      expect(link.getAttribute('href')).not.toContain('/configuration');
    }
  });

  it('sends no empty state, on a populated node, to /configuration either', async () => {
    serveScenario('populated');

    await renderAutonomy();

    for (const link of screen.queryAllByTestId('way-back')) {
      expect(link.getAttribute('href')).not.toContain('/configuration');
    }
  });

  it('points the rules panel’s empty state at the rule-creation section on this same page', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy();

    const link = screen.getByTestId('way-back');
    expect(link).toHaveAttribute('href', '#new-rule');
    expect(document.getElementById('new-rule')).toBeInTheDocument();
  });
});
