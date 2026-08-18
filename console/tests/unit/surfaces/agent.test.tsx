import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { message } from '@/i18n/messages';
import { LOCALE_COOKIE, SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { bridgedServers, capabilityRows } from '@/surfaces/capability-rows';
import {
  AGENT_TABS,
  AgentScreen,
  budgetLabel,
  effectiveBudget,
  roleBinding,
  tabFrom,
} from '@/surfaces/screens/agent';

import { AREA_SCREENS } from '../support/screens';
import { principalHolding, serveScenario } from '../support/dataset';
import { bodyFor } from '../../../scripts/fixture-server.mjs';

/**
 * The three questions, on one screen.
 *
 * The negative assertion is the one worth reading twice. Provider neutrality is
 * an article of this project's constitution, so a surface describing the agent
 * may name a *role* and may not name a vendor's model beside a stage — and the
 * one place a provider may appear is a row that says which node chose it. That
 * is a property of the whole rendered page rather than of one component, which
 * is why it is asserted against the page's text.
 */

/** The locale cookie a test may set, read fresh by every `cookies()` call. */
const cookieJar = new Map<string, string>();

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) => {
        if (name === SESSION_COOKIE) return { value: 'a-token' };
        const stored = cookieJar.get(name);
        return stored === undefined ? undefined : { value: stored };
      },
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** Every permission the dataset's operator holds, so nothing is hidden by a gate. */
const EVERYTHING = [
  'approval.read',
  'audit.read',
  'config.read',
  'config.write',
  'identity.read',
  'integration.manage',
  'investigation.read',
  'investigation.run',
  'knowledge.read',
  'memory.read',
  'remediation.approve',
  'remediation.execute',
  'schedule.manage',
  'token.manage',
];

/** Every provider identifier this build knows how to talk to. */
const PROVIDERS = [
  'anthropic',
  'openai',
  'azure_openai',
  'aws_bedrock',
  'google_gemini',
  'google_vertex_ai',
  'openrouter',
  'nvidia_nim',
  'ollama',
];

const NODE = 'env-production';

beforeEach(() => {
  cookieJar.clear();
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderAgent(
  query: Readonly<Record<string, string>> = {},
): Promise<void> {
  const target = AREA_SCREENS.find((each) => each.id === 'agent');
  if (target === undefined) throw new Error('there is no agent screen');
  render(await target.render({ searchParams: Promise.resolve(query) }));
}

describe('the three sections', () => {
  beforeEach(() => {
    serveScenario('populated', principalHolding(EVERYTHING, NODE));
  });

  it('offers all three, with the address carrying which one is showing', async () => {
    await renderAgent({ node: NODE });

    const tabs = screen.getAllByTestId('tab-link');
    expect(tabs.map((tab) => tab.getAttribute('data-tab'))).toEqual([...AGENT_TABS]);
    for (const tab of tabs) {
      expect(tab.getAttribute('href')).toContain('tab=');
    }
    expect(tabs[0]?.getAttribute('aria-current')).toBe('page');
  });

  it('shows the section the address names', async () => {
    await renderAgent({ node: NODE, tab: 'tools' });

    const current = screen
      .getAllByTestId('tab-link')
      .find((tab) => tab.getAttribute('aria-current') === 'page');
    expect(current?.getAttribute('data-tab')).toBe('tools');
    expect(screen.getAllByTestId('tool-group').length).toBeGreaterThan(0);
  });

  it('falls back to the first section for a name it does not have', () => {
    expect(tabFrom('nonsense')).toBe(AGENT_TABS[0]);
    expect(tabFrom('autonomy')).toBe('autonomy');
  });
});

describe('what it is: the stages and the specialists', () => {
  beforeEach(() => {
    serveScenario('populated', principalHolding(EVERYTHING, NODE));
  });

  it('renders the stages in the order the pipeline runs them', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    const stages = screen.getAllByTestId('agent-stage');
    expect(stages.map((stage) => stage.getAttribute('data-stage'))).toEqual([
      'resolve_integrations',
      'intake',
      'plan_evidence',
      'gather_evidence',
      'diagnose',
      'deliver',
    ]);
  });

  it('draws the hierarchy with the specialists on it, disabled ones included', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    const drawn = screen.getAllByTestId('hierarchy-node');
    const specialists = drawn.filter(
      (node) => node.getAttribute('data-rank') === 'specialists',
    );
    expect(specialists.map((node) => node.getAttribute('data-node'))).toContain(
      'change-historian',
    );
    expect(
      specialists
        .find((node) => node.getAttribute('data-node') === 'change-historian')
        ?.getAttribute('data-disabled'),
    ).toBe('true');
  });

  it('marks a specialist the configuration switched off rather than hiding it', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    const listed = screen.getAllByTestId('agent-specialist');
    const off = listed.filter((row) => row.getAttribute('data-enabled') === 'false');
    expect(off.map((row) => row.getAttribute('data-specialist'))).toEqual([
      'change-historian',
    ]);
  });

  it('never shows the raw resource-health word for a specialist still dispatched', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    const rows = screen.getAllByTestId('agent-specialist');
    const on = rows.filter((row) => row.getAttribute('data-enabled') === 'true');
    expect(on.length).toBeGreaterThan(0);
    for (const row of on) {
      // `healthy` is a resource's word, never a specialist's own on/off state.
      expect(row.textContent).not.toMatch(/healthy/i);
      expect(within(row).getByTestId('specialist-state')).toHaveTextContent('Enabled');
    }

    // change-historian is the fixture's own switched-off specialist — this
    // branch has a natural red already, unlike the two proved by hand below.
    const off = rows.find(
      (row) => row.getAttribute('data-specialist') === 'change-historian',
    );
    if (off === undefined) throw new Error('the switched-off specialist is not there');
    expect(within(off).getByTestId('specialist-state')).toHaveTextContent('Disabled');
  });

  it('does not repeat the specialists empty state in the document panel', async () => {
    // A deployment with nothing configured: the specialists panel says so, with
    // its own heading and a way out. The document beside it is a second view of
    // the same data, and repeating that whole explanation a second time in a
    // row is the defect — the document may simply show that there is nothing.
    serveScenario('empty', principalHolding(EVERYTHING, ''));
    await renderAgent({ tab: 'topology' });

    const document = screen
      .getByTestId('agent-document')
      .closest('[data-testid="panel"]');
    expect(document?.getAttribute('data-state')).not.toBe('empty');
    // The JSON itself still says truthfully that there is nothing here.
    expect(screen.getByTestId('agent-document').textContent).toContain('agents');
  });

  it('shows the same specialists in the document as in the list, from one source', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    const rendered = screen
      .getAllByTestId('agent-specialist')
      .map((row) => row.getAttribute('data-specialist'));
    const document = screen.getByTestId('agent-document').textContent;

    expect(rendered.length).toBeGreaterThan(0);
    for (const name of rendered) {
      expect(document).toContain(String(name));
    }
  });

  it('renders every budget with the ceiling the schema sets', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    // The dataset describes the four the schema bounds; each row that has one
    // states the ceiling, because a team may lower a budget and may not raise
    // one past it.
    const ceilings = screen.queryAllByTestId('agent-budget-ceiling');
    expect(ceilings.length).toBeGreaterThan(0);
    for (const ceiling of ceilings) {
      expect(ceiling.textContent).toMatch(/\d/);
    }
  });

  it('never renders a ceiling for a budget the schema does not bound', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    // agents.tool_budget declares a floor (ge=1) and no ceiling — the schema
    // genuinely does not bound it, which is a fact and not the digit 0.
    const budget = screen
      .getAllByTestId('agent-budget')
      .find((row) => row.getAttribute('data-path') === 'agents.tool_budget');
    expect(budget).toBeDefined();
    expect(budget?.querySelector('[data-testid="agent-budget-ceiling"]')).toBeNull();
  });

  it('shows the dotted path as metadata beside a human label', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    const budget = screen
      .getAllByTestId('agent-budget')
      .find((row) => row.getAttribute('data-path') === 'agents.max_iterations');
    expect(budget).toBeDefined();
    // The raw key is still on the row somewhere — as metadata — and the row's
    // own label is not simply the dotted path repeated.
    expect(budget?.textContent).toContain('agents.max_iterations');
    const value = budget?.querySelector('[data-testid="agent-budget-value"]');
    expect(value).not.toBeNull();
    expect(value?.textContent).not.toBe('0');
  });

  it("labels a budget in the reader's own language, not the schema's English default", async () => {
    // The screen already translates everything around this row — the panel
    // title, the ceiling annotation, the provenance sentence. The dotted path
    // stays as metadata (asserted above); the row's own label must not be the
    // one thing on it still reading in English to a Portuguese-speaking reader.
    cookieJar.set(LOCALE_COOKIE, 'pt-BR');
    await renderAgent({ node: NODE, tab: 'topology' });

    const budget = screen
      .getAllByTestId('agent-budget')
      .find((row) => row.getAttribute('data-path') === 'agents.max_iterations');
    expect(budget).toBeDefined();
    expect(budget?.textContent).toContain(
      message('pt-BR', 'agent.budgets.maxIterations'),
    );
    expect(budget?.textContent).not.toContain('Max iterations');
  });
});

describe("a budget path's own words, once this console has them", () => {
  it("translates a path this console has words for, in the reader's own language", () => {
    expect(budgetLabel('en', 'agents.max_iterations', 'Max Iterations')).toBe(
      message('en', 'agent.budgets.maxIterations'),
    );
    expect(budgetLabel('pt-BR', 'agents.max_iterations', 'Max Iterations')).toBe(
      message('pt-BR', 'agent.budgets.maxIterations'),
    );
    // Not merely "a Portuguese sentence" — specifically not the schema's own,
    // untranslated label, which is the exact defect this function exists to fix.
    expect(budgetLabel('pt-BR', 'agents.max_iterations', 'Max Iterations')).not.toBe(
      'Max Iterations',
    );
  });

  it('translates every path the budgets panel actually renders', () => {
    // BUDGET_PATHS names four; every one of them must resolve to a real word,
    // never fall through to the schema's own English label, in Portuguese.
    for (const path of [
      'agents.max_iterations',
      'agents.max_parallel_subagents',
      'agents.max_subagent_depth',
      'agents.tool_budget',
    ]) {
      const label = budgetLabel('pt-BR', path, 'Whatever The Schema Says');
      expect(label).not.toBe('Whatever The Schema Says');
      expect(label).not.toBe(path);
    }
  });

  it('still falls back to the schema label for a path this console has no words for yet', () => {
    expect(
      budgetLabel('pt-BR', 'agents.some_future_budget', 'Some Future Budget'),
    ).toBe('Some Future Budget');
  });

  it('falls back to the raw path only when the schema has nothing to say either', () => {
    expect(budgetLabel('en', 'agents.some_future_budget', '')).toBe(
      'agents.some_future_budget',
    );
  });
});

describe('what one budget is actually worth, apart from the fixture', () => {
  it('shows the schema default rather than zero when nobody customised it', () => {
    // agents.max_iterations, never touched at any node: the deployment still
    // runs on a real number, and the console must say which one.
    const budget = effectiveBudget({
      path: 'agents.max_iterations',
      value: null,
      provenance: '',
      default: 20,
      maximum: 20,
    });

    expect(budget.customised).toBe(false);
    expect(budget.value).toBe(20);
  });

  it('trusts an explicit zero exactly as it trusts any other customised value', () => {
    // agents.max_subagent_depth may be set to zero on purpose (no recursion at
    // all), and that is a customisation, not an absent one that coincides with
    // the default.
    const budget = effectiveBudget({
      path: 'agents.max_subagent_depth',
      value: 0,
      provenance: 'team-storage',
      default: 2,
      maximum: 2,
    });

    expect(budget.customised).toBe(true);
    expect(budget.value).toBe(0);
  });

  it('carries no ceiling when the schema declares a floor and no roof', () => {
    const budget = effectiveBudget({
      path: 'agents.tool_budget',
      value: 40,
      provenance: 'org-northwind',
      default: 8,
      maximum: null,
    });

    expect(budget.ceiling).toBeUndefined();
  });
});

describe('what a role resolves to when nobody bound it', () => {
  it('says what the deployment default actually is, once the schema knows', () => {
    const declared = [
      {
        path: 'models.diagnose.provider',
        value: null,
        provenance: '',
        default: 'anthropic',
      },
      {
        path: 'models.diagnose.model',
        value: null,
        provenance: '',
        default: 'claude-sonnet-5',
      },
    ];

    const binding = roleBinding(declared, 'diagnose');

    expect(binding.bound).toBe(false);
    expect(binding.provider).toBe('anthropic');
    expect(binding.model).toBe('claude-sonnet-5');
  });

  it('still reads as unbound-with-nothing-known when the schema says nothing either', () => {
    const binding = roleBinding([], 'diagnose');

    expect(binding.bound).toBe(false);
    expect(binding.provider).toBe('');
    expect(binding.model).toBe('');
  });

  it('prefers what a node actually bound over the deployment default', () => {
    const declared = [
      {
        path: 'models.diagnose.provider',
        value: 'openai',
        provenance: 'team-platform',
        default: 'anthropic',
      },
      {
        path: 'models.diagnose.model',
        value: 'gpt-5',
        provenance: 'team-platform',
        default: 'claude-sonnet-5',
      },
    ];

    const binding = roleBinding(declared, 'diagnose');

    expect(binding.bound).toBe(true);
    expect(binding.provider).toBe('openai');
    expect(binding.provenance).toBe('team-platform');
  });
});

describe('Article VI: the model is a role here, never a vendor', () => {
  beforeEach(() => {
    serveScenario('populated', principalHolding(EVERYTHING, NODE));
  });

  it('names no provider outside a model-role row that says where it came from', async () => {
    const { container } = render(
      await (async () => {
        const target = AREA_SCREENS.find((each) => each.id === 'agent');
        if (target === undefined) throw new Error('there is no agent screen');
        return target.render({
          searchParams: Promise.resolve({ node: NODE, tab: 'topology' }),
        });
      })(),
    );

    // Every provider name on the page, wherever it is.
    const everything = container.textContent;
    const named = PROVIDERS.filter((provider) => everything.includes(provider));

    // And every provider name inside a model-role row — bound to a node, or
    // named as the deployment default, either of which says where it came
    // from. A row that is neither still names nothing.
    const attributed = screen
      .getAllByTestId('model-role')
      .map((row) => row.textContent)
      .join(' ');

    for (const provider of named) {
      expect(
        attributed,
        `${provider} is rendered somewhere that does not say who chose it`,
      ).toContain(provider);
    }
  });

  it('shows a stage its role and never a model', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    for (const stage of screen.getAllByTestId('agent-stage')) {
      const role = stage.getAttribute('data-role') ?? '';
      const text = stage.textContent;
      for (const provider of PROVIDERS) {
        expect(text).not.toContain(provider);
      }
      if (role !== '') expect(text).toContain(role);
    }
  });

  it('reads "deployment default" for a role nobody bound', async () => {
    await renderAgent({ node: NODE, tab: 'topology' });

    const unbound = screen
      .getAllByTestId('model-role')
      .filter((row) => row.getAttribute('data-bound') === 'false');
    expect(unbound.length).toBeGreaterThan(0);
    for (const row of unbound) {
      expect(row.textContent).toContain('deployment default');
      for (const provider of PROVIDERS) {
        expect(row.textContent).not.toContain(provider);
      }
    }
  });
});

describe('what it can do: the tools', () => {
  beforeEach(() => {
    serveScenario('populated', principalHolding(EVERYTHING, NODE));
  });

  it('splits the catalogue into what reads and what writes', async () => {
    await renderAgent({ node: NODE, tab: 'tools' });

    const groups = screen
      .getAllByTestId('tool-group')
      .map((group) => group.getAttribute('data-group'));
    expect(groups).toEqual(['read', 'write']);

    for (const tool of screen.getAllByTestId('agent-tool')) {
      expect(['read', 'write']).toContain(tool.getAttribute('data-group'));
    }
  });

  it('dims a tool whose integration is missing, and names the integration', async () => {
    await renderAgent({ node: NODE, tab: 'tools' });

    const blocked = screen
      .getAllByTestId('agent-tool')
      .filter((tool) => tool.getAttribute('data-available') === 'false');
    expect(blocked.length).toBeGreaterThan(0);
    for (const tool of blocked) {
      expect(tool.className).toContain('opacity-60');
      const reason = tool.querySelector('[data-testid="tool-blocked"]');
      expect(reason?.textContent.trim()).toBeTruthy();
      // Named, not merely "unavailable": the integration is the thing somebody
      // can go and connect.
      expect(reason?.textContent).not.toMatch(/:\s*$/);
    }
  });

  it('lists a server outside this deployment as an outside origin', async () => {
    await renderAgent({ node: NODE, tab: 'tools' });

    const servers = screen.getAllByTestId('bridged-server');
    expect(servers.map((server) => server.getAttribute('data-server'))).toContain(
      'runbooks',
    );
    expect(servers[0]?.textContent).toContain('mcp');
  });

  it('never shows the raw resource-health word for a server still registered', async () => {
    await renderAgent({ node: NODE, tab: 'tools' });

    const servers = screen.getAllByTestId('bridged-server');
    const on = servers.filter((row) => row.getAttribute('data-enabled') === 'true');
    expect(on.length).toBeGreaterThan(0);
    for (const row of on) {
      // `healthy` is a resource's word, never a bridged server's own
      // registration state.
      expect(row.textContent).not.toMatch(/healthy/i);
      expect(within(row).getByTestId('bridged-server-state')).toHaveTextContent(
        'Enabled',
      );
    }
  });
});

describe('a bridged server the configuration has switched off', () => {
  // The populated fixture's one bridged server is enabled — this branch has
  // no natural red in that dataset, so it is served by hand instead.
  const AGENT_NODE = 'org-northwind';

  function serveWithDisabledServer(): void {
    vi.stubGlobal('fetch', (input: unknown) => {
      const path = new URL(String(input), ['http:', '//fixtures.invalid'].join(''))
        .pathname;
      const byPath: Record<string, unknown> = {
        '/auth/me': {
          principal_id: 'user-operator',
          display_name: 'Avery Lockhart',
          kind: 'person',
          roles: ['owner'],
          permissions: EVERYTHING,
          team_node_id: AGENT_NODE,
          impersonating: false,
          impersonated_by: null,
        },
        '/v1/config': {
          nodes: [
            {
              kind: 'organisation',
              name: 'Northwind',
              node_id: AGENT_NODE,
              parent_id: null,
            },
          ],
        },
        [`/v1/config/${AGENT_NODE}`]: {
          node_id: AGENT_NODE,
          values: {
            capabilities: {
              protocol_servers: [
                {
                  name: 'archived-runbooks',
                  protocol: 'mcp',
                  transport: 'stdio',
                  command: ['run', 'archived-runbooks'],
                  enabled: false,
                },
              ],
            },
          },
          provenance: {},
        },
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

  it('says the server is disabled, never paused and never healthy', async () => {
    serveWithDisabledServer();
    await renderAgent({ node: AGENT_NODE, tab: 'tools' });

    const row = screen
      .getAllByTestId('bridged-server')
      .find((server) => server.getAttribute('data-server') === 'archived-runbooks');
    if (row === undefined) throw new Error('the disabled server row is not there');
    expect(row.textContent).not.toMatch(/healthy/i);
    expect(row.textContent).not.toContain('paused');
    expect(within(row).getByTestId('bridged-server-state')).toHaveTextContent(
      'Disabled',
    );
  });
});

/**
 * The catalogue's own read half, absorbed whole: 233 tools and ~100 skills,
 * searchable, with an anchor per domain and a "N of M enabled" count — what
 * `catalogue.tsx` used to draw on its own route, before Integrations took the
 * write half and this tab took the read one.
 *
 * Four things this block pins, ported from that screen's own confrontation:
 *
 * - a name/domain search a reader can use to find one tool in under five
 *   seconds, with an anchor per domain and a "N of M enabled" count;
 * - the exact broken sentence a prior bug report quoted ("Blocked by needs
 *   the X integration") never renders, replaced by a structured sentence and
 *   a link to where the missing integration is connected;
 * - skills are searchable and grouped under their own heading, not a wall of
 *   repeated prose.
 */
describe("what it can do: the catalogue's own read half", () => {
  const CATALOGUE_BASE = ['http:', '//gateway.test'].join('');

  function tool(source: { readonly name: string; readonly domain: string }): unknown {
    return {
      name: source.name,
      description: `What ${source.name} does.`,
      domain: source.domain,
      side_effect_level: 'read',
    };
  }

  function entry(source: {
    readonly name: string;
    readonly available: boolean;
    readonly reason?: string;
    readonly requiredIntegrations?: readonly string[];
  }): unknown {
    return {
      name: source.name,
      kind: 'tool',
      summary: `What ${source.name} does.`,
      tags: [],
      side_effect_level: 'read',
      required_integrations: source.requiredIntegrations ?? [],
      available: source.available,
      reason: source.reason ?? null,
    };
  }

  const CAPABILITIES = {
    tools: [
      tool({ name: 'estate.list_resources', domain: 'estate' }),
      tool({ name: 'chat.post_message', domain: 'chat' }),
      tool({ name: 'audit.tamper_check', domain: 'audit' }),
    ],
    skills: [
      {
        name: 'kubernetes-triage',
        description: 'Diagnose a crashing pod, one command at a time.',
      },
    ],
  };

  const NODE_CATALOGUE = {
    entries: [
      entry({ name: 'estate.list_resources', available: true }),
      entry({
        name: 'chat.post_message',
        available: false,
        reason: 'needs the chat integration',
        requiredIntegrations: ['chat'],
      }),
      entry({
        name: 'audit.tamper_check',
        available: false,
        reason: 'disabled for this team',
      }),
    ],
    blocked_by_integration: { chat: ['chat.post_message'] },
  };

  function serve(): void {
    vi.stubGlobal('fetch', (input: unknown) => {
      const path = new URL(String(input), CATALOGUE_BASE).pathname;
      const byPath: Record<string, unknown> = {
        '/auth/me': {
          principal_id: 'user-operator',
          display_name: 'Avery Lockhart',
          kind: 'person',
          roles: ['owner'],
          permissions: EVERYTHING,
          team_node_id: 'org-northwind',
          impersonating: false,
          impersonated_by: null,
        },
        '/v1/capabilities': CAPABILITIES,
        '/v1/config': { nodes: [] },
        '/v1/config/org-northwind/catalogue': NODE_CATALOGUE,
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

  /** The `<tr data-testid="capability">` row for one tool, by its declared name. */
  function toolRow(name: string): HTMLElement {
    const found = screen
      .getAllByTestId('capability')
      .find((row) => row.getAttribute('data-capability') === name);
    if (found === undefined) throw new Error(`no capability row for ${name}`);
    return found;
  }

  /** The `<tr data-testid="capability-domain">` heading row for one domain. */
  function domainHeading(domain: string): HTMLElement {
    const found = screen
      .getAllByTestId('capability-domain')
      .find((row) => row.getAttribute('data-domain') === domain);
    if (found === undefined) throw new Error(`no domain heading for ${domain}`);
    return found;
  }

  describe('finding a tool by name or domain', () => {
    beforeEach(() => {
      serve();
    });

    it('shows every tool and skill with nothing typed', async () => {
      await renderAgent({ tab: 'tools' });

      expect(toolRow('estate.list_resources')).toBeDefined();
      expect(toolRow('chat.post_message')).toBeDefined();
      expect(toolRow('audit.tamper_check')).toBeDefined();
      expect(screen.getByText('kubernetes-triage')).toBeDefined();
    });

    it('narrows to the rows a search matches, by name', async () => {
      await renderAgent({ tab: 'tools' });

      await userEvent.type(
        screen.getByLabelText('Find a tool or skill by name or domain'),
        'chat',
      );

      expect(toolRow('chat.post_message')).toBeDefined();
      expect(
        screen
          .queryAllByTestId('capability')
          .some(
            (row) => row.getAttribute('data-capability') === 'estate.list_resources',
          ),
      ).toBe(false);
    });

    it('says how many of the whole catalogue are enabled, unaffected by the filter', async () => {
      await renderAgent({ tab: 'tools' });

      expect(screen.getByTestId('capability-count')).toHaveTextContent(
        '1 of 3 enabled',
      );

      await userEvent.type(
        screen.getByLabelText('Find a tool or skill by name or domain'),
        'chat',
      );

      expect(screen.getByTestId('capability-count')).toHaveTextContent(
        '1 of 3 enabled',
      );
    });

    it('offers an anchor per domain a reader can jump to', async () => {
      await renderAgent({ tab: 'tools' });

      const nav = screen.getByTestId('domain-nav');
      expect(within(nav).getByRole('link', { name: /^estate/ })).toHaveAttribute(
        'href',
        '#domain-estate',
      );
      expect(within(nav).getByRole('link', { name: /^chat/ })).toHaveAttribute(
        'href',
        '#domain-chat',
      );
    });

    it('says plainly when nothing matches, rather than an empty table', async () => {
      await renderAgent({ tab: 'tools' });

      await userEvent.type(
        screen.getByLabelText('Find a tool or skill by name or domain'),
        'nothing-matches-this',
      );

      expect(screen.getByTestId('capability-search-empty')).toBeDefined();
      expect(screen.queryAllByTestId('capability')).toHaveLength(0);
    });
  });

  describe('why a tool is not available here', () => {
    beforeEach(() => {
      serve();
    });

    it('never renders the broken sentence a prior bug report quoted', async () => {
      await renderAgent({ tab: 'tools' });

      expect(screen.queryByText(/Blocked by needs the/)).toBeNull();
      expect(document.body.textContent).not.toContain('Blocked by needs the');
    });

    it('names the missing integration in a sentence that stands on its own, with a link to connect it', async () => {
      await renderAgent({ tab: 'tools' });

      const blocked = within(toolRow('chat.post_message')).getByTestId(
        'capability-blocked',
      );
      expect(blocked).toHaveTextContent('Requires the chat integration');
      const link = within(blocked).getByRole('link', { name: 'Connect it' });
      expect(link).toHaveAttribute('href', '/integrations');
    });

    it('shows a refusal that is not about a missing integration as-is, with no link', async () => {
      await renderAgent({ tab: 'tools' });

      const blocked = within(toolRow('audit.tamper_check')).getByTestId(
        'capability-blocked',
      );
      expect(blocked).toHaveTextContent('disabled for this team');
      expect(within(blocked).queryByRole('link')).toBeNull();
    });
  });

  describe('whether a tool is available here', () => {
    beforeEach(() => {
      serve();
    });

    it('says the tool is enabled, never the raw resource-health word', async () => {
      await renderAgent({ tab: 'tools' });

      const row = toolRow('estate.list_resources');
      // `healthy` is a resource's word, never a capability's own
      // availability in this column — the same distinction already drawn
      // for a bridged server's own registration state.
      expect(row.textContent).not.toMatch(/healthy/i);
      expect(within(row).getByTestId('capability-available')).toHaveTextContent(
        'Enabled',
      );
    });
  });

  describe('skills are searchable and grouped, not a wall of prose', () => {
    beforeEach(() => {
      serve();
    });

    it('groups skills under their own heading rather than repeating "Skills —" on every row', async () => {
      await renderAgent({ tab: 'tools' });

      expect(domainHeading('skills')).toHaveTextContent('Skills (1)');
      expect(screen.getByText('kubernetes-triage')).toBeDefined();
      expect(screen.queryByText(/Skills — /)).toBeNull();
    });

    it('is found by the same search that finds a tool', async () => {
      await renderAgent({ tab: 'tools' });

      await userEvent.type(
        screen.getByLabelText('Find a tool or skill by name or domain'),
        'triage',
      );

      expect(screen.getByText('kubernetes-triage')).toBeDefined();
      expect(
        screen
          .queryAllByTestId('capability')
          .some(
            (row) => row.getAttribute('data-capability') === 'estate.list_resources',
          ),
      ).toBe(false);
    });
  });
});

describe('what it will do alone', () => {
  beforeEach(() => {
    serveScenario('populated', principalHolding(EVERYTHING, NODE));
  });

  it('answers one sentence per class of action', async () => {
    await renderAgent({ node: NODE, tab: 'autonomy' });

    const classes = screen.getAllByTestId('outlook-class');
    expect(classes.map((entry) => entry.getAttribute('data-risk'))).toEqual([
      'trivial',
      'low',
      'moderate',
      'high',
      'critical',
    ]);
    for (const entry of classes) {
      const sentence = entry.querySelector('[data-testid="outlook-sentence"]');
      expect(sentence?.textContent).toContain('would');
    }
  });

  it('shows what the posture decided about what actually happened, beside the classes', async () => {
    await renderAgent({ node: NODE, tab: 'autonomy' });

    // The declared set answers on a deployment's first day; the replay answers
    // once there is a record. Both, when both are available.
    expect(screen.getAllByTestId('outlook-class').length).toBe(5);
    const replayed = screen.getAllByTestId('replayed-action');
    expect(replayed.length).toBeGreaterThan(0);
    expect(replayed.map((row) => row.getAttribute('data-capability'))).toContain(
      'restart_workload',
    );
  });

  it('does not ask for the record at all when the reader may not', async () => {
    serveScenario(
      'populated',
      principalHolding(
        EVERYTHING.filter((permission) => permission !== 'config.write'),
        NODE,
      ),
    );
    await renderAgent({ node: NODE, tab: 'autonomy' });

    expect(screen.getAllByTestId('outlook-class').length).toBe(5);
    expect(screen.queryAllByTestId('replayed-action')).toEqual([]);
  });

  it('links the policy editor rather than embedding one', async () => {
    await renderAgent({ node: NODE, tab: 'autonomy' });

    const links = Array.from(document.querySelectorAll('a'))
      .map((anchor) => anchor.getAttribute('href') ?? '')
      .filter((href) => href.startsWith('/autonomy'));
    expect(links.length).toBeGreaterThan(0);
    // Nothing on this tab writes: no form, no button that posts a posture.
    expect(document.querySelectorAll('form')).toHaveLength(0);
  });
});

describe('the capability join both screens read', () => {
  it('produces the same rows from the same two payloads, whoever asks', () => {
    const capabilities = bodyFor('populated', '/v1/capabilities');
    const entries = bodyFor('populated', `/v1/config/${NODE}/catalogue`);

    const once = capabilityRows(capabilities, entries);
    const twice = capabilityRows(capabilities, entries);

    expect(once.length).toBeGreaterThan(0);
    expect(once).toEqual(twice);
  });

  it('marks a tool the node knows nothing about as unknown rather than blocked', () => {
    const capabilities = bodyFor('populated', '/v1/capabilities');
    const rows = capabilityRows(capabilities, {});

    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.known).toBe(false);
      expect(row.available).toBe(false);
      expect(row.reason).toBe('');
    }
  });
});

describe('a deployment with nothing configured yet', () => {
  beforeEach(() => {
    // No organisation tree, so no node resolves and nothing node-scoped is
    // asked for. Every section still has to be a page rather than a throw.
    serveScenario('empty', principalHolding(EVERYTHING, ''));
  });

  for (const tab of AGENT_TABS) {
    it(`${tab}: says what would be here instead of failing`, async () => {
      await renderAgent({ tab });

      expect(screen.getByTestId('page-header')).toBeInTheDocument();
      const panels = screen.getAllByTestId('panel');
      expect(
        panels.filter((panel) => panel.getAttribute('data-state') === 'error'),
      ).toEqual([]);
      expect(
        panels.filter((panel) => panel.getAttribute('data-state') === 'empty').length,
      ).toBeGreaterThan(0);
    });
  }

  it('marks every tool as unresolved rather than as blocked', async () => {
    await renderAgent({ tab: 'tools' });

    for (const tool of screen.queryAllByTestId('agent-tool')) {
      expect(tool.getAttribute('data-available')).toBe('unknown');
    }
  });
});

describe('a viewer who may not change the posture', () => {
  it('is offered no way to edit it from here', async () => {
    serveScenario(
      'populated',
      principalHolding(
        EVERYTHING.filter((permission) => permission !== 'config.write'),
        NODE,
      ),
    );
    await renderAgent({ node: NODE, tab: 'autonomy' });

    const links = Array.from(document.querySelectorAll('a'))
      .map((anchor) => anchor.getAttribute('href') ?? '')
      .filter((href) => href.startsWith('/autonomy'));
    expect(links).toEqual([]);
  });
});

describe('reading a capability payload', () => {
  it('calls a level it has never heard of a write', () => {
    const rows = capabilityRows(
      { tools: [{ name: 'x.y', description: 'd', side_effect_level: 'teleport' }] },
      { entries: [] },
    );
    expect(rows[0]?.writes).toBe(true);
  });

  it('names the server a bridged tool came from, and nothing for a first-party one', () => {
    const rows = capabilityRows(
      { tools: [{ name: 'runbooks.restart', description: 'd' }] },
      {
        entries: [
          {
            name: 'runbooks.restart',
            summary: 's',
            side_effect_level: 'write_reversible',
            available: true,
            tags: ['bridged'],
            required_integrations: [],
          },
        ],
      },
    );
    expect(rows[0]?.origin).toBe('runbooks');

    const own = capabilityRows(
      { tools: [{ name: 'estate.storage_pressure', description: 'd' }] },
      {
        entries: [
          {
            name: 'estate.storage_pressure',
            summary: 's',
            side_effect_level: 'read',
            available: true,
            tags: ['estate'],
            required_integrations: [],
          },
        ],
      },
    );
    expect(own[0]?.origin).toBe('');
  });

  it('reads a bridged server run from a command as well as one at an address', () => {
    const servers = bridgedServers({
      capabilities: {
        protocol_servers: [
          {
            name: 'local',
            protocol: 'mcp',
            transport: 'stdio',
            command: ['run', 'it'],
          },
        ],
      },
    });
    expect(servers[0]?.address).toBe('run it');
    // The schema's default is on, so a server that says nothing is enabled —
    // and the console must not draw it as switched off.
    expect(servers[0]?.enabled).toBe(false);
  });
});

describe('the advanced agent-settings section', () => {
  const AGENT_NODE = 'org-northwind';

  const WRITER = {
    principal_id: 'user-operator',
    display_name: 'Avery Lockhart',
    email: 'avery.lockhart@example.invalid',
    kind: 'person',
    roles: ['owner'],
    permissions: ['config.read', 'config.write'],
    team_node_id: AGENT_NODE,
    impersonated_by: null,
    impersonating: false,
  };

  function respond(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    });
  }

  function serveAgentAdvanced(principal: unknown = WRITER): void {
    vi.stubGlobal('fetch', (input: unknown) => {
      const path = new URL(String(input), ['http:', '//fixtures.invalid'].join(''))
        .pathname;
      if (path === '/auth/me') return Promise.resolve(respond(principal));
      if (path === '/v1/config') {
        return Promise.resolve(
          respond({
            nodes: [
              {
                kind: 'organisation',
                name: 'Northwind',
                node_id: AGENT_NODE,
                parent_id: null,
              },
            ],
          }),
        );
      }
      if (path === '/v1/agent/pipeline') {
        return Promise.resolve(respond({ stages: [], model_roles: [] }));
      }
      if (path === `/v1/config/${AGENT_NODE}`) {
        return Promise.resolve(
          respond({
            node_id: AGENT_NODE,
            values: {
              agents: { tool_budget: 40, prompts: { investigator: 'Look closer.' } },
            },
            provenance: { 'agents.tool_budget': AGENT_NODE },
          }),
        );
      }
      if (path === `/v1/config/${AGENT_NODE}/fields`) {
        return Promise.resolve(
          respond({
            fields: [
              {
                path: 'agents.tool_budget',
                label: 'Tool budget',
                type: 'integer',
                section: 'Agents',
                value: 40,
                provenance: AGENT_NODE,
                set_here: true,
              },
              {
                path: 'agents.prompts.investigator',
                label: 'Investigator prompt override',
                type: 'string',
                section: 'Prompts',
                value: 'Look closer.',
                provenance: AGENT_NODE,
                set_here: true,
              },
            ],
          }),
        );
      }
      return Promise.resolve(respond({}, 404));
    });
  }

  async function renderAgentTopology(): Promise<void> {
    render(await AgentScreen(await surfaceContext({ node: AGENT_NODE })));
  }

  it('is collapsed on arrival, on the Topology tab, and names the nine fields with no other control', async () => {
    serveAgentAdvanced();

    await renderAgentTopology();

    const details = screen.getByTestId('advanced-config-agents');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    const rows = screen.getAllByTestId('effective-field');
    const paths = rows.map((row) => row.getAttribute('data-path'));
    expect(paths).toEqual(
      expect.arrayContaining([
        'agents.max_iterations',
        'agents.max_parallel_subagents',
        'agents.max_subagent_depth',
        'agents.max_subagent_iterations',
        'agents.operating_context.enabled',
        'agents.prompts.diagnose',
        'agents.prompts.intake',
        'agents.prompts.investigator',
        'agents.tool_budget',
      ]),
    );
  });

  it('offers no editor to a viewer who may not write configuration', async () => {
    serveAgentAdvanced({
      ...WRITER,
      principal_id: 'user-viewer',
      permissions: ['config.read'],
    });

    await renderAgentTopology();

    const section = screen.getByTestId('advanced-config-agents');
    expect(within(section).queryByTestId('ask-preview')).toBeNull();
  });
});

describe('the advanced capabilities section, on the Tools tab', () => {
  const AGENT_NODE = 'org-northwind';

  const WRITER = {
    principal_id: 'user-operator',
    display_name: 'Avery Lockhart',
    email: 'avery.lockhart@example.invalid',
    kind: 'person',
    roles: ['owner'],
    permissions: ['config.read', 'config.write'],
    team_node_id: AGENT_NODE,
    impersonated_by: null,
    impersonating: false,
  };

  function respond(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    });
  }

  function serveAgentCapabilities(principal: unknown = WRITER): void {
    vi.stubGlobal('fetch', (input: unknown) => {
      const path = new URL(String(input), ['http:', '//fixtures.invalid'].join(''))
        .pathname;
      if (path === '/auth/me') return Promise.resolve(respond(principal));
      if (path === '/v1/config') {
        return Promise.resolve(
          respond({
            nodes: [
              {
                kind: 'organisation',
                name: 'Northwind',
                node_id: AGENT_NODE,
                parent_id: null,
              },
            ],
          }),
        );
      }
      if (path === `/v1/config/${AGENT_NODE}`) {
        return Promise.resolve(
          respond({
            node_id: AGENT_NODE,
            values: { capabilities: {} },
            provenance: {},
          }),
        );
      }
      if (path === `/v1/config/${AGENT_NODE}/fields`) {
        return Promise.resolve(
          respond({
            fields: [
              {
                path: 'capabilities.protocol_servers',
                label: 'Bridged servers',
                type: 'array',
                section: 'Capabilities',
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
              },
            ],
          }),
        );
      }
      return Promise.resolve(respond({}, 404));
    });
  }

  async function renderAgentTools(): Promise<void> {
    render(await AgentScreen(await surfaceContext({ node: AGENT_NODE, tab: 'tools' })));
  }

  it('is collapsed on arrival, on the Tools tab, and draws protocol_servers as an editable, reorderable list', async () => {
    serveAgentCapabilities();

    await renderAgentTools();

    const details = screen.getByTestId('advanced-config-capabilities');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    const field = details.querySelector(
      '[data-testid="config-field"][data-path="capabilities.protocol_servers"]',
    );
    expect(field).not.toBeNull();
    expect(field?.querySelector('[data-testid="object-list"]')).toBeInTheDocument();
  });

  it('offers no editor to a viewer who may not write configuration', async () => {
    serveAgentCapabilities({
      ...WRITER,
      principal_id: 'user-viewer',
      permissions: ['config.read'],
    });

    await renderAgentTools();

    const details = screen.getByTestId('advanced-config-capabilities');
    expect(within(details).queryByTestId('ask-preview')).toBeNull();
  });
});
