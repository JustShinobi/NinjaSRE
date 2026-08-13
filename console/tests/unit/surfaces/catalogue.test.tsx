import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { CatalogueScreen } from '@/surfaces/screens/catalogue';

/**
 * 233 tools, ~100 skills, and 85 credential forms on one route — the page
 * spec 025 confronts. Four things this file pins:
 *
 * - a name/domain search a reader can use to find one tool in under five
 *   seconds, with an anchor per domain and a "N of M enabled" count;
 * - the exact broken sentence the bug report quotes ("Blocked by needs the
 *   X integration") never renders, replaced by a structured sentence and a
 *   link to where the missing integration is connected;
 * - every credential form starts collapsed, with nothing about it visible
 *   until an operator asks for it;
 * - each integration's real state — absent, stored, verified, failing — is
 *   legible off the collapsed card alone.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

const BASE = ['http:', '//gateway.test'].join('');

function principal(permissions: readonly string[]): unknown {
  return {
    principal_id: 'user-operator',
    display_name: 'Avery Lockhart',
    kind: 'person',
    roles: ['owner'],
    permissions,
    team_node_id: 'org-northwind',
    impersonating: false,
    impersonated_by: null,
  };
}

function tool(source: { readonly name: string; readonly domain: string }): unknown {
  return {
    name: source.name,
    description: `What ${source.name} does.`,
    domain: source.domain,
    side_effect_level: 'read',
  };
}

/** A resolved node catalogue entry — what `/v1/config/{node}/catalogue` names. */
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

function integration(source: {
  readonly name: string;
  readonly health: string;
  readonly healthDetail?: string;
}): unknown {
  return {
    name: source.name,
    category: 'observability',
    summary: `What ${source.name} is for.`,
    hosts: [],
    regions: [],
    capabilities: [],
    required_credentials: ['api_key'],
    required_permissions: [],
    health: source.health,
    health_detail: source.healthDetail ?? '',
    parity: 'full',
    missing_artefacts: [],
    suggested: null,
  };
}

const INTEGRATIONS = {
  integrations: [
    integration({ name: 'prometheus', health: 'unconfigured' }),
    integration({ name: 'datadog', health: 'unknown' }),
    integration({
      name: 'chat',
      health: 'healthy',
      healthDetail: 'verified 3 hours ago',
    }),
    integration({
      name: 'ticketing',
      health: 'degraded',
      healthDetail: 'the last verification timed out',
    }),
  ],
  known_gaps: [],
};

function serve(bodies: {
  readonly permissions?: readonly string[];
  readonly capabilities?: unknown;
  readonly nodeCatalogue?: unknown;
  readonly integrations?: unknown;
}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const byPath: Record<string, unknown> = {
      '/auth/me': principal(bodies.permissions ?? ['integration.manage']),
      '/v1/capabilities': bodies.capabilities ?? CAPABILITIES,
      '/v1/config': { nodes: [] },
      '/v1/config/org-northwind/catalogue': bodies.nodeCatalogue ?? NODE_CATALOGUE,
      '/v1/integrations': bodies.integrations ?? INTEGRATIONS,
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

async function catalogue(): Promise<void> {
  render(await CatalogueScreen(await surfaceContext({})));
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

/** The collapsed card for one integration, by name. */
function integrationCard(name: string): HTMLElement {
  const found = screen
    .getAllByTestId('integration')
    .find((card) => card.getAttribute('data-integration') === name);
  if (found === undefined) throw new Error(`no integration card for ${name}`);
  return found;
}

describe('finding a tool by name or domain', () => {
  beforeEach(() => {
    serve({});
  });

  it('shows every tool and skill with nothing typed', async () => {
    await catalogue();

    expect(toolRow('estate.list_resources')).toBeDefined();
    expect(toolRow('chat.post_message')).toBeDefined();
    expect(toolRow('audit.tamper_check')).toBeDefined();
    expect(screen.getByText('kubernetes-triage')).toBeDefined();
  });

  it('narrows to the rows a search matches, by name', async () => {
    await catalogue();

    await userEvent.type(
      screen.getByLabelText('Find a tool or skill by name or domain'),
      'chat',
    );

    expect(toolRow('chat.post_message')).toBeDefined();
    expect(
      screen
        .queryAllByTestId('capability')
        .some((row) => row.getAttribute('data-capability') === 'estate.list_resources'),
    ).toBe(false);
    expect(
      screen
        .queryAllByTestId('capability')
        .some((row) => row.getAttribute('data-capability') === 'audit.tamper_check'),
    ).toBe(false);
  });

  it('narrows to the rows a search matches, by domain', async () => {
    await catalogue();

    await userEvent.type(
      screen.getByLabelText('Find a tool or skill by name or domain'),
      'estate',
    );

    expect(toolRow('estate.list_resources')).toBeDefined();
    expect(
      screen
        .queryAllByTestId('capability')
        .some((row) => row.getAttribute('data-capability') === 'chat.post_message'),
    ).toBe(false);
  });

  it('says how many of the whole catalogue are enabled, unaffected by the filter', async () => {
    await catalogue();

    expect(screen.getByTestId('capability-count')).toHaveTextContent('1 of 3 enabled');

    await userEvent.type(
      screen.getByLabelText('Find a tool or skill by name or domain'),
      'chat',
    );

    expect(screen.getByTestId('capability-count')).toHaveTextContent('1 of 3 enabled');
  });

  it('offers an anchor per domain a reader can jump to', async () => {
    await catalogue();

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
    await catalogue();

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
    serve({});
  });

  it('never renders the broken sentence the bug report quotes', async () => {
    await catalogue();

    expect(screen.queryByText(/Blocked by needs the/)).toBeNull();
    expect(document.body.textContent).not.toContain('Blocked by needs the');
  });

  it('names the missing integration in a sentence that stands on its own, with a link to connect it', async () => {
    await catalogue();

    const blocked = within(toolRow('chat.post_message')).getByTestId(
      'capability-blocked',
    );
    expect(blocked).toHaveTextContent('Requires the chat integration');
    const link = within(blocked).getByRole('link', { name: 'Connect it' });
    expect(link).toHaveAttribute('href', '/configuration?node=org-northwind');
  });

  it('shows a refusal that is not about a missing integration as-is, with no link', async () => {
    await catalogue();

    const blocked = within(toolRow('audit.tamper_check')).getByTestId(
      'capability-blocked',
    );
    expect(blocked).toHaveTextContent('disabled for this team');
    expect(within(blocked).queryByRole('link')).toBeNull();
  });
});

describe('a credential form is collapsed until asked for', () => {
  beforeEach(() => {
    serve({});
  });

  it('shows every integration state without expanding anything', async () => {
    await catalogue();

    expect(integrationCard('prometheus').getAttribute('data-state')).toBe(
      'unconfigured',
    );
    expect(
      within(integrationCard('prometheus')).getByText(/No credential is stored/),
    ).toBeDefined();

    expect(integrationCard('datadog').getAttribute('data-state')).toBe('unknown');
    expect(
      within(integrationCard('datadog')).getByText(/nothing has checked it yet/),
    ).toBeDefined();

    expect(integrationCard('chat').getAttribute('data-state')).toBe('healthy');
    expect(within(integrationCard('chat')).getByText(/Verified/)).toBeDefined();
    expect(
      within(integrationCard('chat')).getByText(/verified 3 hours ago/),
    ).toBeDefined();

    expect(integrationCard('ticketing').getAttribute('data-state')).toBe('degraded');
    expect(within(integrationCard('ticketing')).getByText(/Failing/)).toBeDefined();
  });

  it('renders no credential form and no verify control before anything is expanded', async () => {
    await catalogue();

    expect(screen.queryAllByTestId('credential')).toHaveLength(0);
    expect(screen.queryAllByTestId('verify-row')).toHaveLength(0);
  });

  it('reveals the form and the verify control for one card, and only that one, once expanded', async () => {
    await catalogue();

    await userEvent.click(
      within(integrationCard('prometheus')).getByTestId('integration-toggle'),
    );

    expect(screen.getAllByTestId('credential')).toHaveLength(1);
    expect(screen.getByTestId('credential')).toHaveAttribute(
      'data-integration',
      'prometheus',
    );
    expect(screen.getAllByTestId('verify-row')).toHaveLength(1);
    expect(screen.getByTestId('verify-row')).toHaveAttribute(
      'data-thing',
      'prometheus',
    );
  });
});

describe('skills are searchable and grouped, not a wall of prose', () => {
  beforeEach(() => {
    serve({});
  });

  it('groups skills under their own heading rather than repeating "Skills —" on every row', async () => {
    await catalogue();

    expect(domainHeading('skills')).toHaveTextContent('Skills (1)');
    expect(screen.getByText('kubernetes-triage')).toBeDefined();
    expect(screen.queryByText(/Skills — /)).toBeNull();
  });

  it('is found by the same search that finds a tool', async () => {
    await catalogue();

    await userEvent.type(
      screen.getByLabelText('Find a tool or skill by name or domain'),
      'triage',
    );

    expect(screen.getByText('kubernetes-triage')).toBeDefined();
    expect(
      screen
        .queryAllByTestId('capability')
        .some((row) => row.getAttribute('data-capability') === 'estate.list_resources'),
    ).toBe(false);
  });
});
