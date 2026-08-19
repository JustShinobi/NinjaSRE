import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { surfaceContext } from '@/surfaces/context';
import { AutonomyScreen } from '@/surfaces/settings/autonomy';

import { serveScenario } from '../../support/dataset';

// The floor in `tests/unit/setup.ts` already stubs `next/navigation` with a
// no-op `refresh` — this file's own mock wins over it (its own comment says
// so) and keeps the same shape, only making `refresh` a spy: the inline
// guardrail editor calls it after a save, so Set at can catch up with what
// was just written, and that call is part of what this file proves.
const refresh = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh, push: () => undefined, replace: () => undefined }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

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
 *
 * The screen is now three tabs (`autonomy-tabs.ts`), each its own address —
 * `renderAutonomy` below passes `tab` alongside every other filter, and each
 * test names the tab that owns whatever it is asserting on, rather than
 * assuming everything still renders on one page load.
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

beforeEach(() => {
  refresh.mockClear();
});

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
  /**
   * The `answer` a POST to the autonomy write endpoint carries back, for
   * `preview`/`explain`/`save`/`dry-run` alike. Undefined means this stub has
   * nothing to say about that endpoint, so tests that never click a simulation
   * control keep getting the same 404 they always did.
   */
  readonly simulationAnswer?: unknown;
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
  simulationAnswer,
}: Stub): void {
  vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
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
    if (path === '/api/autonomy' && init?.method === 'POST') {
      return simulationAnswer === undefined
        ? Promise.resolve(respond({}, 404))
        : Promise.resolve(respond({ ok: true, answer: simulationAnswer }));
    }
    return Promise.resolve(respond({}, 404));
  });
}

function emptyPanels(): HTMLElement[] {
  return screen
    .getAllByTestId('panel')
    .filter((panel) => panel.getAttribute('data-state') === 'empty');
}

describe('the three tabs, addressable and marked', () => {
  it('renders Posture, Rules & windows and Guardrails in that order, each a real link, and marks the one this address named', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'guardrails' });

    const links = screen.getAllByTestId('tab-link');
    expect(links).toHaveLength(3);
    expect(links.map((link) => link.textContent)).toEqual([
      'Posture',
      'Rules & windows',
      'Guardrails',
    ]);

    // A link with its own address, not a button that only flips client
    // state: the browser's own history has to record the switch, which only
    // an anchor with a real `href` gives for free.
    for (const link of links) {
      expect(link.tagName).toBe('A');
    }
    expect(links[0]).toHaveAttribute('href', expect.stringContaining('tab=posture'));
    expect(links[1]).toHaveAttribute(
      'href',
      expect.stringContaining('tab=rules-windows'),
    );
    expect(links[2]).toHaveAttribute('href', expect.stringContaining('tab=guardrails'));

    // The active tab is the one this address named — the other two carry no
    // `aria-current` at all, never a falsy one.
    expect(links[2]).toHaveAttribute('aria-current', 'page');
    expect(links[0]).not.toHaveAttribute('aria-current');
    expect(links[1]).not.toHaveAttribute('aria-current');
  });
});

describe('a node with no rule and no bound recorded', () => {
  it('shows exactly one empty panel, with the first-rule editor directly beneath it', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'rules-windows' });

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

  it('suppresses the bounds panel on Posture too, rather than repeating the same "nothing recorded"', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'posture' });

    // Genuine suppression, not the structural absence every other tab shows:
    // the node resolved (`org-northwind`, `SINGLE_NODE`'s default), so the
    // panel would appear here if it had anything to say — it stays off only
    // because both rules and bounds are empty at once.
    expect(
      screen.queryByRole('heading', { name: 'Bounds and level overrides' }),
    ).not.toBeInTheDocument();
  });

  it('leaves the editor out for a viewer who may not write', async () => {
    serveAutonomy({ principal: READER, policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'rules-windows' });

    expect(emptyPanels()).toHaveLength(1);
    expect(screen.queryByTestId('autonomy-editor')).not.toBeInTheDocument();
  });

  it('leaves the override panel out, on its own tab, for a viewer who may not write', async () => {
    serveAutonomy({ principal: READER, policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'posture' });

    expect(screen.queryByTestId('override-editor')).not.toBeInTheDocument();
  });
});

describe('the vocabulary this screen assumes an operator already has', () => {
  it('no longer bundles the three concepts into one glossary block at the top of any tab', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'rules-windows' });
    expect(screen.queryByTestId('autonomy-glossary')).not.toBeInTheDocument();

    await renderAutonomy({ tab: 'posture' });
    expect(screen.queryByTestId('autonomy-glossary')).not.toBeInTheDocument();
  });

  it('defines a rule where one is created, on Rules & windows', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'rules-windows' });

    expect(screen.getByTestId('autonomy-rule-note')).toHaveTextContent(/rule/i);
  });

  it('defines a bound on Posture, beside the panel that shows it', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'posture' });

    expect(screen.getByTestId('autonomy-bound-note')).toHaveTextContent(/bound/i);
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

    const user = userEvent.setup();
    await renderAutonomy();
    // The panel is a rare action now: nothing about it is on the page until
    // the header button opens it.
    await user.click(screen.getByRole('button', { name: /temporary override/i }));

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

    const user = userEvent.setup();
    await renderAutonomy();
    await user.click(screen.getByRole('button', { name: /temporary override/i }));

    expect(screen.queryByTestId('revoke-override')).not.toBeInTheDocument();
    // The sentence, not merely the absence of a row: an empty list and a
    // list that says nothing would both leave `active-override` absent.
    expect(screen.getByTestId('override-revoke-empty')).toHaveTextContent(
      /no override is active/i,
    );
  });
});

describe('the temporary override, behind a header button', () => {
  it.each(['posture', 'rules-windows', 'guardrails'] as const)(
    'reserves no body space for it, tab=%s',
    async (tab) => {
      serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

      await renderAutonomy({ tab });

      // Not merely "no button visible" — the editor itself, and the sentence
      // that used to sit beside it on Posture, are gone from the body on
      // every tab, not hidden on the one tab they used to live on.
      expect(screen.queryByTestId('override-editor')).not.toBeInTheDocument();
      expect(screen.queryByTestId('autonomy-override-note')).not.toBeInTheDocument();
    },
  );

  it('opens from a button inside the page header, carrying name, level, reason and duration, the reason field naming the audit trail', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });
    const user = userEvent.setup();

    await renderAutonomy();

    const header = screen.getByTestId('page-header');
    const trigger = within(header).getByRole('button', {
      name: /temporary override/i,
    });
    await user.click(trigger);

    const dialog = screen.getByRole('dialog', { name: /temporary override/i });
    expect(within(dialog).getByLabelText('Name')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Level')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Duration')).toBeInTheDocument();
    // The reason field's own label, not a caption beside it, is what has to
    // say this — a single lookup proves both that the field exists and that
    // its label names the audit trail.
    expect(within(dialog).getByLabelText(/reason.*audit trail/i)).toBeInTheDocument();
    // The definition that used to sit in Posture's body moved with the
    // control it explains, into the panel it now belongs to.
    expect(within(dialog).getByTestId('autonomy-override-note')).toHaveTextContent(
      /override/i,
    );
  });

  it('carries no trigger at all for a viewer who may not write', async () => {
    serveAutonomy({ principal: READER, policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy();

    expect(
      screen.queryByRole('button', { name: /temporary override/i }),
    ).not.toBeInTheDocument();
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

    await renderAutonomy({ tab: 'rules-windows' });

    expect(emptyPanels()).toHaveLength(1);
    expect(screen.queryByTestId('autonomy-editor')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Bounds and level overrides' }),
    ).not.toBeInTheDocument();
  });

  it('shows no override panel either, with no node to scope it to', async () => {
    serveAutonomy({
      tree: [],
      principal: { ...WRITER, team_node_id: '' },
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'posture' });

    expect(screen.queryByTestId('override-editor')).not.toBeInTheDocument();
  });
});

describe('no rule recorded, but a freeze window is', () => {
  const BOUNDS_WITH_A_FREEZE = {
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
  };

  it('still shows only one empty panel on Rules & windows', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: BOUNDS_WITH_A_FREEZE });

    await renderAutonomy({ tab: 'rules-windows' });

    expect(emptyPanels()).toHaveLength(1);
  });

  it('keeps the bounds panel’s real content, on Posture where it now lives', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: BOUNDS_WITH_A_FREEZE });

    await renderAutonomy({ tab: 'posture' });

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

    // The stopped row moved to Posture with the rest of the bounds panel —
    // "is everything switched off" is exactly the posture reading.
    await renderAutonomy({ tab: 'posture' });

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

    await renderAutonomy({ tab: 'posture' });

    expect(screen.getByTestId('autonomy-stopped')).toHaveTextContent(
      'Automated writes are stopped for this organisation',
    );
    expect(screen.queryByTestId('release-stop')).not.toBeInTheDocument();
    expect(screen.queryByTestId('engage-stop')).not.toBeInTheDocument();
  });
});

describe('a populated node', () => {
  it('renders nothing as empty on Rules & windows', async () => {
    serveScenario('populated');

    await renderAutonomy({ tab: 'rules-windows' });

    expect(emptyPanels()).toHaveLength(0);
    expect(screen.getByTestId('autonomy-footer')).toBeInTheDocument();
  });

  it('renders the bounds panel and the override panel as not-empty either, on Posture', async () => {
    serveScenario('populated');

    await renderAutonomy({ tab: 'posture' });

    expect(emptyPanels()).toHaveLength(0);
    // The bounds panel — freeze, budget and override rows — lives here now,
    // carrying real content rather than the panel this tab used to render
    // (the override editor) alone.
    expect(
      screen.getByRole('heading', { name: 'Bounds and level overrides' }),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId('bound').length).toBeGreaterThan(0);
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

    await renderAutonomy({ tab: 'rules-windows' });

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

describe('rule, freeze and cap creation, all reached from the same tab', () => {
  it('brings all three creation controls onto Rules & windows', async () => {
    serveAutonomy({
      policy: {
        ...EMPTY_POLICY,
        rules: [
          { rule_id: 'r1', scope: { kind: 'deployment' }, level: 'propose_only' },
        ],
      },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'rules-windows' });

    expect(screen.getByTestId('new-rule')).toBeInTheDocument();
    expect(screen.getByTestId('new-freeze')).toBeInTheDocument();
    expect(screen.getByTestId('new-budget')).toBeInTheDocument();
  });
});

describe('the rules list, in resolution order regardless of the order the deployment sent it in', () => {
  it('renders least-specific first even when the deployment sends the most specific rule first', async () => {
    serveAutonomy({
      policy: {
        ...EMPTY_POLICY,
        // Deliberately sent most-specific first — the reverse of resolution
        // order — so a missing or broken sort would render this exact order
        // instead of being masked by an already-sorted fixture.
        rules: [
          {
            rule_id: 'r7',
            scope: {
              kind: 'capability_resource',
              capability: 'estate.restart',
              resource_id: 'vm-9',
            },
            level: 'act_on_low_risk',
            risk_bound: 'low',
          },
          {
            rule_id: 'r6',
            scope: { kind: 'resource', resource_id: 'vm-9' },
            level: 'propose_only',
          },
          {
            rule_id: 'r5',
            scope: { kind: 'capability', capability: 'estate.restart' },
            level: 'act_and_report',
          },
          {
            rule_id: 'r4',
            scope: { kind: 'labels', labels: { tier: 'critical' } },
            level: 'propose_only',
          },
          {
            rule_id: 'r3',
            scope: { kind: 'resource_kind', resource_kind: 'vm' },
            level: 'propose_only',
          },
          {
            rule_id: 'r2',
            scope: { kind: 'team', team_node_id: 'team-payments' },
            level: 'propose_only',
          },
          { rule_id: 'r1', scope: { kind: 'deployment' }, level: 'propose_only' },
        ],
      },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'rules-windows' });

    const rows = screen.getAllByTestId('autonomy-rule');
    expect(rows).toHaveLength(7);
    // The scope-kind cell, read in row order — not a substring match against
    // the whole row, which "capability" would also match inside
    // "capability_resource".
    const kinds = rows.map((row) => row.querySelector('td')?.textContent);
    expect(kinds).toEqual([
      'deployment',
      'team',
      'resource_kind',
      'labels',
      'capability',
      'resource',
      'capability_resource',
    ]);
  });
});

describe('the rules list scrolls on its own, not the whole tab, when a node has many rules', () => {
  it('bounds only the rules list, leaving the creation controls and the simulation section unconstrained', async () => {
    const manyRules = Array.from({ length: 40 }, (_, index) => ({
      rule_id: `r${String(index)}`,
      scope: { kind: 'resource', resource_id: `vm-${String(index)}` },
      level: 'propose_only',
    }));
    serveAutonomy({
      policy: { ...EMPTY_POLICY, rules: manyRules },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'rules-windows' });

    const rows = screen.getAllByTestId('autonomy-rule');
    expect(rows).toHaveLength(40);

    const scrollRegion = screen.getByTestId('rules-scroll');
    expect(scrollRegion.className).toMatch(/overflow-(y-)?auto/);
    expect(scrollRegion.className).toMatch(/max-h-/);
    for (const row of rows) {
      expect(scrollRegion).toContainElement(row);
    }

    // The boundary is drawn narrowly around the list: the rest of the tab is
    // a sibling of the scrolling region, never a descendant swallowed by it.
    const simulation = screen.getByTestId('autonomy-simulation');
    expect(scrollRegion).not.toContainElement(simulation);
    expect(scrollRegion.contains(simulation)).toBe(false);
  });
});

describe('the simulation section, on Rules & windows', () => {
  const ONE_RULE = {
    rule_id: 'r1',
    scope: { kind: 'deployment' },
    level: 'propose_only',
  };

  it('has its own title, a line saying what it answers, and exactly one primary CTA, with none of the old competing labels surviving beside it', async () => {
    serveAutonomy({
      policy: { ...EMPTY_POLICY, rules: [ONE_RULE] },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'rules-windows' });

    const section = screen.getByTestId('autonomy-simulation');
    expect(
      within(section).getByRole('heading', { name: 'Simulate this change' }),
    ).toBeInTheDocument();
    expect(section).toHaveTextContent(
      'Replays what this node has actually decided recently',
    );

    // A count, not a find: the defect this replaces was three controls of
    // equal weight, a shape "a primary exists somewhere" cannot rule out.
    const primaries = within(section)
      .getAllByRole('button')
      .filter((button) => button.getAttribute('data-variant') === 'primary');
    expect(primaries).toHaveLength(1);

    // The absence has to be proven, not the presence of the survivor: each
    // of yesterday's three labels is checked for a non-primary match, the
    // same shape the feature's own acceptance spec counts.
    for (const name of [
      'Explain one action',
      'Simulate everything',
      'Stop simulating',
      'What would this decide differently?',
    ]) {
      const matches = within(section).queryAllByRole('button', { name });
      const survivors = matches.filter(
        (button) => button.getAttribute('data-variant') !== 'primary',
      );
      expect(survivors, `"${name}" survives outside the primary CTA`).toHaveLength(0);
    }
  });

  it('still refuses to save the current rule until its simulated effect has been seen', async () => {
    const PREVIEW_ANSWER = {
      summary: 'One of one action would be decided differently.',
      considered: 1,
      changed: 1,
      newly_autonomous: 0,
      actions: [],
    };
    serveAutonomy({
      policy: { ...EMPTY_POLICY, rules: [ONE_RULE] },
      bounds: EMPTY_BOUNDS,
      simulationAnswer: PREVIEW_ANSWER,
    });

    await renderAutonomy({ tab: 'rules-windows' });

    const row = screen.getByTestId('rule-editor');
    await userEvent.selectOptions(
      within(row).getByLabelText('Level'),
      'act_and_report',
    );

    // Edited, but not yet previewed: no save control exists for this entry.
    expect(screen.queryByTestId('save-autonomy')).toBeNull();
    expect(screen.getByTestId('autonomy-preview-first')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));
    expect(await screen.findByTestId('save-autonomy')).toBeInTheDocument();

    // Editing again after the preview was seen takes the save away again —
    // the lock is against the *current* entry, not a one-time unlock.
    await userEvent.selectOptions(within(row).getByLabelText('Level'), 'propose_only');
    expect(screen.queryByTestId('save-autonomy')).toBeNull();
  });
});

describe('the guardrails section', () => {
  it('shows masking, guardrail and approval fields with their effective value and origin', async () => {
    // Every row's value and origin now come from the deployment's own field
    // catalogue (`/v1/config/{node}/fields`) rather than from the effective-
    // configuration document's `values`/`provenance` — the source that used
    // to leave a row blank whenever nothing had overridden it, because that
    // document does not carry a field's schema default. `masking.enabled` is
    // overridden at this node; the rest resolve to their own schema default,
    // and `ruleset` has none declared at all.
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: {},
      fields: [
        {
          path: 'policies.masking.enabled',
          label: 'Masking enabled',
          type: 'boolean',
          section: 'Masking',
          value: true,
          default: false,
          provenance: NODE,
          set_here: true,
        },
        {
          path: 'policies.masking.level',
          label: 'Masking level',
          type: 'string',
          section: 'Masking',
          value: 'strict',
          default: 'strict',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.guardrails.mode',
          label: 'Secret detection',
          type: 'string',
          section: 'Guardrails',
          value: 'enforcing',
          default: 'enforcing',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.guardrails.ruleset',
          label: 'Detection ruleset',
          type: 'string',
          section: 'Guardrails',
          value: null,
          default: null,
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.approvals.threshold',
          label: 'Approval threshold',
          type: 'string',
          section: 'Approvals',
          value: 'write_reversible',
          default: 'write_reversible',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.approvals.expiry_hours',
          label: 'Approval expiry',
          type: 'integer',
          section: 'Approvals',
          value: 4.5,
          default: 4.5,
          provenance: '',
          set_here: false,
        },
      ],
    });

    await renderAutonomy({ tab: 'guardrails' });

    function rowFor(path: string): HTMLElement {
      const row = screen
        .getAllByTestId('effective-field')
        .find((each) => each.getAttribute('data-path') === path);
      if (row === undefined) throw new Error(`no effective-field row for ${path}`);
      return row;
    }

    // A boolean reads as a state a reader can act on, never the payload
    // literal — "On", not "true".
    expect(rowFor('policies.masking.enabled')).toHaveTextContent('On');
    expect(rowFor('policies.masking.enabled')).not.toHaveTextContent('true');
    expect(rowFor('policies.masking.enabled')).toHaveTextContent(NODE);
    expect(rowFor('policies.masking.level')).toHaveTextContent('strict');
    expect(rowFor('policies.masking.level')).toHaveTextContent('Deployment default');
    expect(rowFor('policies.guardrails.mode')).toHaveTextContent('enforcing');
    // `ruleset` has no override and no schema default — the row still exists,
    // naming the field, with an explicit "not set" marker rather than a
    // blank cell, which the component itself refuses to render.
    expect(rowFor('policies.guardrails.ruleset')).toHaveTextContent('Not set');
    expect(rowFor('policies.approvals.threshold')).toHaveTextContent(
      'write_reversible',
    );
    // A duration is said as one — "4.5 hours" — never the bare number alone.
    expect(rowFor('policies.approvals.expiry_hours')).toHaveTextContent('4.5 hours');
    // The Setting column names the field, not just its value — the walk a
    // reader does is "what is this, what is it set to, where from", and the
    // first of those three still has to be there after the tab cut.
    expect(rowFor('policies.masking.level')).toHaveTextContent('Masking level');
    // Value and Set at say different things for the same row — surviving the
    // tab cut is the property T018 verifies, not merely that neither is
    // blank (`EffectiveFieldsTable`'s own throw already forecloses that).
    for (const path of [
      'policies.masking.enabled',
      'policies.masking.level',
      'policies.guardrails.mode',
      'policies.approvals.threshold',
      'policies.approvals.expiry_hours',
    ]) {
      const r = rowFor(path);
      const value = r.querySelector('td:nth-child(2)')?.textContent ?? '';
      const origin = r.querySelector('td:nth-child(3)')?.textContent ?? '';
      expect(value).not.toBe('');
      expect(origin).not.toBe('');
      expect(value).not.toBe(origin);
    }
    // The two constitutional invariants are stated as facts, never as a toggle.
    const invariants = screen.getAllByTestId('guardrail-invariant');
    expect(invariants).toHaveLength(2);
    // No generic editor at all on this tab: the six fields this fixture
    // declares are exactly the six `GUARDRAIL_FIELDS` already draws inline,
    // above, so there is nothing left for it to offer. The advanced
    // autonomy-scalars editor this same test dataset also feeds lives on
    // Rules & windows now, not here; see the advanced-autonomy-scalars
    // `describe` below for that one.
    expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
    // A display name is shown, but that alone does not prove
    // the raw technical path is gone — the two can coexist. It does not,
    // anywhere on this tab.
    expect(document.body.textContent).not.toMatch(
      /\bpolicies\.(masking|guardrails|approvals)\b/,
    );
  });

  it('leaves the editor out, keeping the read-only rows, for a viewer who may not write', async () => {
    serveAutonomy({
      principal: READER,
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: { policies: { masking: { enabled: false, level: 'standard' } } },
    });

    await renderAutonomy({ tab: 'guardrails' });

    expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('effective-field').length).toBeGreaterThan(0);
    // A reader gets the value and its origin, never the form that
    // would write it — not the generic editor below (checked above) and not
    // this table's own inline affordance either.
    expect(screen.queryByTestId('guardrail-edit')).not.toBeInTheDocument();
    expect(screen.queryByTestId('guardrail-field-editor')).not.toBeInTheDocument();
  });

  it('keeps the three array-shaped fields reachable through the generic editor, now that the six scalars have their own row', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: {},
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
        {
          path: 'policies.masking.custom_patterns',
          label: 'Custom patterns',
          type: 'array',
          section: 'Masking',
          value: [],
          provenance: '',
          set_here: false,
          item_fields: [
            {
              path: 'pattern',
              label: 'Pattern',
              type: 'string',
              help: '',
              allowed_values: null,
              minimum: null,
              maximum: null,
              default: '',
            },
          ],
        },
        {
          path: 'policies.guardrails.disabled_rules',
          label: 'Disabled rules',
          type: 'array',
          section: 'Guardrails',
          value: [],
          provenance: '',
          set_here: false,
          item_fields: [
            {
              path: 'rule_id',
              label: 'Rule',
              type: 'string',
              help: '',
              allowed_values: null,
              minimum: null,
              maximum: null,
              default: '',
            },
          ],
        },
        {
          path: 'policies.approvals.autonomous_capabilities',
          label: 'Autonomous capabilities',
          type: 'array',
          section: 'Approvals',
          value: [],
          provenance: '',
          set_here: false,
          item_fields: [
            {
              path: 'capability',
              label: 'Capability',
              type: 'string',
              help: '',
              allowed_values: null,
              minimum: null,
              maximum: null,
              default: '',
            },
          ],
        },
      ],
    });

    await renderAutonomy({ tab: 'guardrails' });

    const editor = screen.getByTestId('config-editor');
    const paths = [...editor.querySelectorAll('[data-testid="config-field"]')].map(
      (each) => each.getAttribute('data-path'),
    );
    expect(paths).toEqual(
      expect.arrayContaining([
        'policies.masking.custom_patterns',
        'policies.guardrails.disabled_rules',
        'policies.approvals.autonomous_capabilities',
      ]),
    );
    // Every scalar `GUARDRAIL_FIELDS` names moved to this table's own row —
    // a path never carries two controls for the same field at once.
    expect(paths).not.toContain('policies.masking.enabled');
    // No tab opens with this generic, multi-section editor as its primary
    // content: three fields is what is left of it here, not the nine this
    // route used to route through it.
    expect(paths).toHaveLength(3);
  });

  it('renders no generic editor at all when the six scalars above already cover every guardrail-prefixed field', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: {},
      fields: [
        {
          path: 'policies.masking.enabled',
          label: 'Masking enabled',
          type: 'boolean',
          section: 'Masking',
          value: true,
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.masking.level',
          label: 'Masking level',
          type: 'string',
          section: 'Masking',
          value: 'strict',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.guardrails.mode',
          label: 'Secret detection',
          type: 'string',
          section: 'Guardrails',
          value: 'enforcing',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.guardrails.ruleset',
          label: 'Detection ruleset',
          type: 'string',
          section: 'Guardrails',
          value: null,
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.approvals.threshold',
          label: 'Approval threshold',
          type: 'string',
          section: 'Approvals',
          value: 'write_reversible',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.approvals.expiry_hours',
          label: 'Approval expiry',
          type: 'integer',
          section: 'Approvals',
          value: 4.5,
          provenance: '',
          set_here: false,
        },
      ],
    });

    await renderAutonomy({ tab: 'guardrails' });

    // A search box for a field list with nothing left to offer is dead UI
    // stating something false to every reader — absent, not an empty
    // result.
    expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
    expect(screen.queryByTestId('search-empty')).not.toBeInTheDocument();
    // The table above still carries the six scalars — the tab itself is
    // not empty, only the generic editor beneath it has nothing left to add.
    expect(screen.getAllByTestId('effective-field').length).toBeGreaterThan(0);
  });

  it('still renders the generic editor when a guardrail-prefixed field is left over, so the fix is a condition rather than a deletion', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: {},
      fields: [
        {
          path: 'policies.masking.enabled',
          label: 'Masking enabled',
          type: 'boolean',
          section: 'Masking',
          value: true,
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.masking.level',
          label: 'Masking level',
          type: 'string',
          section: 'Masking',
          value: 'strict',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.guardrails.mode',
          label: 'Secret detection',
          type: 'string',
          section: 'Guardrails',
          value: 'enforcing',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.guardrails.ruleset',
          label: 'Detection ruleset',
          type: 'string',
          section: 'Guardrails',
          value: null,
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.approvals.threshold',
          label: 'Approval threshold',
          type: 'string',
          section: 'Approvals',
          value: 'write_reversible',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.approvals.expiry_hours',
          label: 'Approval expiry',
          type: 'integer',
          section: 'Approvals',
          value: 4.5,
          provenance: '',
          set_here: false,
        },
        // The one field left over once the six scalars above have their own
        // row — the same shape the fix still has to draw, not merely stop
        // hiding.
        {
          path: 'policies.masking.custom_patterns',
          label: 'Custom patterns',
          type: 'array',
          section: 'Masking',
          value: [],
          provenance: '',
          set_here: false,
          item_fields: [
            {
              path: 'pattern',
              label: 'Pattern',
              type: 'string',
              help: '',
              allowed_values: null,
              minimum: null,
              maximum: null,
              default: '',
            },
          ],
        },
      ],
    });

    await renderAutonomy({ tab: 'guardrails' });

    const editor = screen.getByTestId('config-editor');
    expect(
      editor.querySelector(
        '[data-testid="config-field"][data-path="policies.masking.custom_patterns"]',
      ),
    ).not.toBeNull();
  });

  it('states the fixed guardrails as facts with no control beside them, and moves the group’s own sentence after the table it describes', async () => {
    serveScenario('populated');

    await renderAutonomy({ tab: 'guardrails' });

    const invariants = screen.getAllByTestId('guardrail-invariant');
    expect(invariants).toHaveLength(2);
    // A fact, stated as one — no switch, no button, nothing to press beside
    // either sentence.
    for (const invariant of invariants) {
      expect(within(invariant).queryByRole('switch')).not.toBeInTheDocument();
      expect(within(invariant).queryByRole('button')).not.toBeInTheDocument();
      expect(invariant.textContent).not.toBe('');
    }

    // The paragraph the mockup shows directly under the title is gone from
    // there — it now sits after the table it introduces, the same "sentence
    // after the control" placement the rule/bound/override notes already use.
    expect(firstParagraphBeforeControl()).toBeNull();
    const note = screen.getByTestId('guardrail-note');
    expect(note).toHaveTextContent('Masking, secret detection and approval');
    const table = screen.getByTestId('effective-fields');
    const bodyOrder = Array.from(document.body.querySelectorAll('*'));
    expect(bodyOrder.indexOf(note)).toBeGreaterThan(bodyOrder.indexOf(table));
  });
});

describe('a reader sees real content on every tab, never an empty page because the only content was write-gated', () => {
  it.each(['posture', 'rules-windows', 'guardrails'] as const)(
    'tab=%s renders values a reader can read, with no form and no override button anywhere on it',
    async (tab) => {
      serveScenario('populated', READER);

      await renderAutonomy({ tab });

      // No write surface reaches a reader, on any tab.
      expect(screen.queryByTestId('autonomy-editor')).not.toBeInTheDocument();
      expect(screen.queryByTestId('posture-editor')).not.toBeInTheDocument();
      expect(screen.queryByTestId('override-editor')).not.toBeInTheDocument();
      expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
      expect(screen.queryByTestId('guardrail-edit')).not.toBeInTheDocument();
      // Not merely the editor absent, but no button offering it either —
      // the header carries the same content on every tab, so this is the
      // one place a reader could otherwise find a route into a form they
      // may not submit.
      expect(
        screen.queryByRole('button', { name: /temporary override/i }),
      ).not.toBeInTheDocument();

      // And the tab is not simply blank instead: each one still has its own
      // real content for a reader to look at.
      if (tab === 'posture') {
        expect(screen.getByTestId('posture-guardrails-summary')).toBeInTheDocument();
        expect(screen.getAllByTestId('effective-field').length).toBeGreaterThan(0);
      }
      if (tab === 'rules-windows') {
        expect(screen.getAllByTestId('autonomy-rule').length).toBeGreaterThan(0);
      }
      if (tab === 'guardrails') {
        expect(screen.getAllByTestId('effective-field').length).toBeGreaterThan(0);
        expect(screen.getAllByTestId('guardrail-invariant')).toHaveLength(2);
      }
    },
  );
});

describe('the advanced autonomy-scalars section', () => {
  it('is collapsed on arrival and names the four fields with no other control', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: {
        policies: {
          autonomy: {
            allow_unverifiable_actions: false,
            dry_run: true,
            recurrence_threshold: 2,
            recurrence_window_seconds: 3600,
          },
        },
      },
      provenance: { 'policies.autonomy.dry_run': NODE },
      fields: [
        {
          path: 'policies.autonomy.dry_run',
          label: 'Dry run',
          type: 'boolean',
          section: 'Autonomy',
          value: true,
          provenance: NODE,
          set_here: true,
        },
      ],
    });

    await renderAutonomy({ tab: 'rules-windows' });

    const details = screen.getByTestId('advanced-config-policies-autonomy');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    const rows = screen.getAllByTestId('effective-field');
    const paths = rows.map((row) => row.getAttribute('data-path'));
    expect(paths).toContain('policies.autonomy.allow_unverifiable_actions');
    expect(paths).toContain('policies.autonomy.dry_run');
    expect(paths).toContain('policies.autonomy.recurrence_threshold');
    expect(paths).toContain('policies.autonomy.recurrence_window_seconds');
  });

  it('scopes its editor to policies.autonomy fields only, never the guardrail ones', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: { policies: { autonomy: { dry_run: false } } },
      provenance: {},
      fields: [
        {
          path: 'policies.autonomy.dry_run',
          label: 'Dry run',
          type: 'boolean',
          section: 'Autonomy',
          value: false,
          provenance: '',
          set_here: false,
        },
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

    await renderAutonomy({ tab: 'rules-windows' });

    const section = screen.getByTestId('advanced-config-policies-autonomy');
    const fieldsInSection = section.querySelectorAll('[data-testid="config-field"]');
    const pathsInSection = [...fieldsInSection].map((field) =>
      field.getAttribute('data-path'),
    );
    expect(pathsInSection).toEqual(['policies.autonomy.dry_run']);
  });

  // The four array-shaped autonomy fields have a purpose-built form of their
  // own (`AutonomyEditor`, `OverrideEditor`, above) — but they also draw
  // through this same prefixed `ConfigEditor` as an `ObjectList`, because the
  // schema describes what one entry of each looks like. This pins that the
  // second, generic route is a genuine answer too, not merely an assumption.
  const AUTONOMY_LIST_PATHS = [
    'policies.autonomy.rules',
    'policies.autonomy.freezes',
    'policies.autonomy.budgets',
    'policies.autonomy.overrides',
  ] as const;

  function listField(path: string): unknown {
    return {
      path,
      label: path,
      type: 'array',
      section: 'Autonomy',
      value: [],
      provenance: '',
      set_here: false,
      item_fields: [
        {
          path: 'name',
          label: 'Name',
          type: 'string',
          help: '',
          allowed_values: null,
          minimum: null,
          maximum: null,
          default: '',
        },
      ],
    };
  }

  it('draws every autonomy list — rules, freezes, budgets and overrides — as an editable, reorderable list too', async () => {
    serveAutonomy({
      policy: EMPTY_POLICY,
      bounds: EMPTY_BOUNDS,
      values: { policies: { autonomy: {} } },
      fields: AUTONOMY_LIST_PATHS.map((path) => listField(path)),
    });

    await renderAutonomy({ tab: 'rules-windows' });

    const section = screen.getByTestId('advanced-config-policies-autonomy');
    for (const path of AUTONOMY_LIST_PATHS) {
      const field = section.querySelector(
        `[data-testid="config-field"][data-path="${path}"]`,
      );
      expect(field).not.toBeNull();
      expect(field?.querySelector('[data-testid="object-list"]')).toBeInTheDocument();
    }
  });
});

describe('the loop into the raw editor', () => {
  it('sends no empty state, on an empty node, to /configuration', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'rules-windows' });

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

    await renderAutonomy({ tab: 'rules-windows' });

    const link = screen.getByTestId('way-back');
    expect(link).toHaveAttribute('href', '#new-rule');
    expect(document.getElementById('new-rule')).toBeInTheDocument();
  });

  it('lands on the live rule-creation control, not merely an id that happens to exist somewhere', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'rules-windows' });

    const link = screen.getByTestId('way-back');
    expect(link).toHaveTextContent('Create the first rule');

    const target = document.getElementById('new-rule');
    if (target === null) throw new Error('the #new-rule target was not rendered');
    // The target is the actual "Create a rule" control, reachable right
    // there, with its own submit button inside it — never a decoy anchor
    // that merely shares the id's name while the real control sits
    // elsewhere.
    expect(within(target).getByTestId('add-rule')).toBeInTheDocument();
  });
});

describe('the bounds panel’s empty state, now that the panel reads on a different tab than the freeze editor', () => {
  it('points at the freeze-creation section on Rules & windows by tab, not a bare anchor absent from Posture', async () => {
    // A rule exists (so the page does not fall into the rules-panel's own
    // empty state instead), but nothing bounds it yet — the one combination
    // that puts the bounds panel itself into its empty state.
    serveAutonomy({
      policy: {
        ...EMPTY_POLICY,
        rules: [
          { rule_id: 'r1', scope: { kind: 'deployment' }, level: 'propose_only' },
        ],
      },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'posture' });

    const link = screen.getByTestId('way-back');
    const href = link.getAttribute('href') ?? '';
    expect(href).toContain('tab=rules-windows');
    expect(href).toContain('#new-freeze');
    // Proven false, not merely asserted: an anchor with no matching id on
    // this render is exactly the "already compliant screen reads red" trap —
    // `#new-freeze` only exists inside `AutonomyEditor`, which this tab does
    // not render, so a same-page anchor here would silently go nowhere.
    expect(document.getElementById('new-freeze')).not.toBeInTheDocument();
  });
});

/**
 * The exact walk `autonomy-tabs.acceptance.spec.ts` runs in the browser,
 * against jsdom instead — one violation message (a paragraph's own text) or
 * `null` when a real control is reached first. Mirrored rather than
 * reimplemented from scratch, so a unit run and a browser run never disagree
 * about what "before the first control" means.
 */
function firstParagraphBeforeControl(): string | null {
  const headerEl = document.querySelector('[data-testid="page-header"]');
  if (headerEl === null) return 'no page-header found';

  const all = Array.from(document.body.querySelectorAll('*'));
  let index = all.indexOf(headerEl);
  if (index === -1) return 'page-header is not attached under body';

  const CHROME_TESTIDS = ['page-header', 'tab-links'];
  for (;;) {
    const root = all[index];
    if (root === undefined) break;
    while (index + 1 < all.length && root.contains(all[index + 1] ?? null)) {
      index += 1;
    }
    const next = all[index + 1];
    const nextTestid = next === undefined ? null : next.getAttribute('data-testid');
    if (nextTestid === null || !CHROME_TESTIDS.includes(nextTestid)) break;
    index += 1;
  }

  const CONTROL_TAGS = new Set(['INPUT', 'SELECT', 'BUTTON', 'TEXTAREA', 'A']);
  for (let cursor = index + 1; cursor < all.length; cursor += 1) {
    const el = all[cursor];
    if (el === undefined) continue;
    if (el.tagName === 'P')
      return `a paragraph sits before the first control: "${el.textContent.trim().slice(0, 120)}"`;
    if (CONTROL_TAGS.has(el.tagName)) return null;
  }
  return null;
}

describe('Posture: the level selector, and nothing before it', () => {
  it('states the node and the posture in force in the subtitle', async () => {
    serveAutonomy({
      policy: {
        ...EMPTY_POLICY,
        rules: [
          {
            rule_id: 'deployment',
            scope: { kind: 'deployment' },
            level: 'act_and_report',
          },
        ],
      },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'posture' });

    const header = screen.getByTestId('page-header');
    expect(header).toHaveTextContent(NODE);
    // The short name, not the bare slug and not the sentence written for
    // the level's own `<Select>` option — that sentence carries its own
    // full stop, and this header is not the control it is summarising.
    expect(header).toHaveTextContent('Act and report');
    expect(header).not.toHaveTextContent('runs on its own');
  });

  it('shows the posture an active override actually puts in force, not the saved level, and says it is temporary', async () => {
    serveAutonomy({
      policy: {
        ...EMPTY_POLICY,
        rules: [
          {
            rule_id: 'deployment',
            scope: { kind: 'deployment' },
            // The saved level is the lowest one — if the subtitle read this
            // instead of the override, it would report the deployment as
            // more cautious than it actually is right now.
            level: 'propose_only',
          },
        ],
      },
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

    await renderAutonomy({ tab: 'posture' });

    const header = screen.getByTestId('page-header');
    // The override's level, not the saved rule's propose-only.
    expect(header).toHaveTextContent('Act and report');
    expect(header).not.toHaveTextContent('Propose only');
    // And it declares why: a temporary override, not the configured posture.
    expect(header).toHaveTextContent(/temporary override/i);
    // The short name only — not the sentence written for the level's own
    // `<Select>` option, and not that sentence's own full stop landing in
    // the middle of this one, right before "from a temporary override".
    expect(header).not.toHaveTextContent('runs on its own');
    expect(header.textContent).not.toMatch(/\.\s*,/);
  });

  it('renders no paragraph between the title and the level selector, on Posture', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'posture' });

    expect(firstParagraphBeforeControl()).toBeNull();
  });

  it('renders no paragraph between the title and the first control, on Rules & windows either', async () => {
    // A node with at least one rule, matching what the browser acceptance
    // suite actually exercises on this tab (`populated`'s every node holds
    // one). With `rules: []` instead, the rules panel draws its own
    // `EmptyState` — heading, then body, then the action — and that body
    // paragraph necessarily precedes the action it explains, the same as
    // every other empty state this design system draws; that is a property
    // of `EmptyState` itself, not the glossary paragraph T015 retires, and
    // is not what this walk is written to prove.
    serveAutonomy({
      policy: {
        ...EMPTY_POLICY,
        rules: [
          {
            rule_id: 'deployment',
            scope: { kind: 'deployment' },
            level: 'propose_only',
          },
        ],
      },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'rules-windows' });

    expect(firstParagraphBeforeControl()).toBeNull();
  });

  it('offers the levels the deployment declares, in display names, with Save beside it', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'posture' });

    const editor = screen.getByTestId('posture-editor');
    const options = Array.from(editor.querySelectorAll('option')).map(
      (option) => option.textContent,
    );
    expect(options).toEqual([
      'Propose only — every action is written up for a person to approve. Nothing runs without one.',
      'Act on low risk — runs on its own up to the risk bound chosen; anything riskier still waits for a person.',
      'Act and report — runs on its own and tells somebody afterwards, whatever the risk.',
      'Act silently — runs on its own and reports nothing. Choose this one deliberately.',
    ]);
    expect(screen.getByTestId('save-posture')).toHaveTextContent('Save posture');
  });

  it('renders a level the screen has no display name for by its declared identifier, never omitted', async () => {
    serveAutonomy({
      policy: {
        ...EMPTY_POLICY,
        rules: [
          {
            rule_id: 'deployment',
            scope: { kind: 'deployment' },
            level: 'custom_level',
          },
        ],
      },
      bounds: EMPTY_BOUNDS,
    });

    await renderAutonomy({ tab: 'posture' });

    const editor = screen.getByTestId('posture-editor');
    const options = Array.from(editor.querySelectorAll('option')).map(
      (option) => option.textContent,
    );
    expect(options).toContain('custom_level');
    // Not merely appended past the four known levels: it is the value this
    // node actually holds, so the control opens on it rather than silently
    // falling back to the first entry.
    expect(editor.querySelector('select')).toHaveValue('custom_level');
  });
});

describe('Posture: the empty state, with no rule recorded', () => {
  it('says everything resolves to propose-only, names it the safe default rather than an error, and points at Rules & windows', async () => {
    serveAutonomy({ policy: EMPTY_POLICY, bounds: EMPTY_BOUNDS });

    await renderAutonomy({ tab: 'posture' });

    const note = screen.getByTestId('autonomy-posture-empty');
    expect(note).toHaveTextContent('everything resolves to propose-only');
    expect(note).toHaveTextContent('safe default rather than an error');

    const link = within(note).getByRole('link', { name: 'Rules & windows' });
    expect(link).toBeInTheDocument();

    // The CTA lands where its own label
    // promises — the Rules & windows tab, not an anchor on the same tab.
    expect(link).toHaveAttribute('href', expect.stringContaining('tab=rules-windows'));
  });

  it('says nothing about the empty default once the node holds a rule', async () => {
    serveScenario('populated');

    await renderAutonomy({ tab: 'posture' });

    expect(screen.queryByTestId('autonomy-posture-empty')).not.toBeInTheDocument();
  });
});
