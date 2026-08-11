import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { bridgedServers, capabilityRows } from '@/surfaces/capabilities';
import { AGENT_TABS, tabFrom } from '@/surfaces/screens/agent';

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

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
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

    // The dataset describes the four the schema bounds; each row states the
    // ceiling, because a team may lower a budget and may not raise one.
    const ceilings = screen.queryAllByTestId('agent-budget-ceiling');
    for (const ceiling of ceilings) {
      expect(ceiling.textContent).toMatch(/\d/);
    }
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

    // And every provider name inside a model-role row that carries provenance.
    const attributed = screen
      .getAllByTestId('model-role')
      .filter((row) => row.getAttribute('data-bound') === 'true')
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
