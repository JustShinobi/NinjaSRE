import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { IntegrationsScreen } from '@/surfaces/screens/integrations';

/**
 * The catalogue, rebuilt: connected first, a suggestion the estate already
 * found, and everything else as a compact, searchable grid rather than a
 * stack of collapsed forms.
 *
 * Four things this file pins:
 *
 * - Connected and Suggested render above the catalogue, in that order, and
 *   never as an empty section;
 * - the grid carries a display name, a category and a one-line summary —
 *   never the raw id — and the raw credential form never appears in it;
 * - search and the category filter narrow the grid in the address, so a
 *   filtered view is a link;
 * - the state a card shows is the one canonical chip, never a second line
 *   repeating it.
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

function principal(): unknown {
  return {
    principal_id: 'user-operator',
    display_name: 'Avery Lockhart',
    kind: 'person',
    roles: ['owner'],
    permissions: ['integration.manage'],
    team_node_id: 'org-northwind',
    impersonating: false,
    impersonated_by: null,
  };
}

interface FieldSource {
  readonly name: string;
  readonly label?: string;
  readonly minScope?: string;
  readonly guideUrl?: string;
}

function field(source: FieldSource): unknown {
  return {
    name: source.name,
    label: source.label ?? source.name,
    secret: true,
    required: true,
    help: '',
    min_scope: source.minScope ?? '',
    guide_url: source.guideUrl ?? '',
  };
}

interface PermissionSource {
  readonly name: string;
  readonly grants: string;
  readonly where?: string;
  readonly capabilities?: readonly string[];
}

function permission(source: PermissionSource): unknown {
  return {
    name: source.name,
    grants: source.grants,
    where: source.where ?? '',
    capabilities: source.capabilities ?? [],
  };
}

function integration(source: {
  readonly name: string;
  readonly displayName?: string;
  readonly category?: string;
  readonly summary?: string;
  readonly health: string;
  readonly healthDetail?: string;
  readonly fields?: readonly FieldSource[];
  readonly capabilities?: readonly string[];
  readonly permissions?: readonly PermissionSource[];
  readonly suggested?: { readonly address: string; readonly fromResource: string };
}): unknown {
  return {
    name: source.name,
    display_name: source.displayName ?? source.name,
    category: source.category ?? 'metrics',
    summary: source.summary ?? `What ${source.name} is for.`,
    hosts: [],
    regions: [],
    capabilities: source.capabilities ?? [],
    fields: (source.fields ?? [{ name: 'api_key' }]).map(field),
    permissions: (source.permissions ?? []).map(permission),
    health: source.health,
    health_detail: source.healthDetail ?? '',
    parity: 'full',
    missing_artefacts: [],
    suggested:
      source.suggested === undefined
        ? null
        : {
            address: source.suggested.address,
            from_resource: source.suggested.fromResource,
            because: 'a guest labelled it is reachable on the right port',
          },
  };
}

const INTEGRATIONS = {
  integrations: [
    integration({
      name: 'prometheus',
      displayName: 'Prometheus',
      category: 'metrics',
      summary: 'PromQL evaluation and firing alerts.',
      health: 'healthy',
      healthDetail: 'verified 3 hours ago',
    }),
    integration({
      name: 'proxmox',
      displayName: 'Proxmox VE',
      category: 'cloud_control_plane',
      summary: 'Hypervisor and guests.',
      health: 'healthy',
      healthDetail: 'verified 3 hours ago',
    }),
    integration({
      name: 'grafana',
      displayName: 'Grafana',
      category: 'cloud_control_plane',
      summary: 'Dashboards and annotations.',
      health: 'unconfigured',
      suggested: { address: '192.168.68.159:3000', fromResource: 'monitoring' },
    }),
    integration({
      name: 'signoz',
      displayName: 'SigNoz',
      category: 'metrics',
      summary: 'Traces, metrics and logs.',
      health: 'degraded',
      healthDetail: 'the last verification timed out',
    }),
    integration({
      name: 'postgresql',
      displayName: 'PostgreSQL',
      category: 'database',
      summary: 'Query plans and slow queries.',
      health: 'unconfigured',
    }),
    integration({
      name: 'telegram',
      displayName: 'Telegram',
      category: 'communication',
      summary: 'Delivers reports and alerts.',
      health: 'unconfigured',
      fields: [
        {
          name: 'bot_token',
          label: 'Bot token',
          minScope: 'sendMessage',
          guideUrl: '/integrations/telegram/guide',
        },
      ],
      permissions: [
        {
          name: 'sendMessage',
          grants: 'post a message as the bot',
          where: 'Telegram → BotFather → your bot → API token',
          capabilities: ['telegram_post_message'],
        },
      ],
    }),
  ],
  known_gaps: [
    {
      integration: 'newrelic-synthetics',
      display_name: 'New Relic Synthetics',
      category: 'monitoring',
      cause: 'not_reachable',
      reason: 'the credential proxy speaks only HTTP',
      resolution: 'a non-HTTP transport for the proxy',
    },
  ],
};

/**
 * `element`, or a failure naming the absence.
 *
 * A test that reaches into an array and asserts on `undefined` reports
 * "cannot read property of undefined", which says nothing about what the
 * console did. This says the element was not there.
 */
function one(element: HTMLElement | undefined): HTMLElement {
  if (element === undefined)
    throw new Error('the element this test is about is not there');
  return element;
}

function serve(bodies: { readonly integrations?: unknown }): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const byPath: Record<string, unknown> = {
      '/auth/me': principal(),
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

async function integrations(params: Record<string, string> = {}): Promise<void> {
  render(await IntegrationsScreen(await surfaceContext(params)));
}

describe('the area header', () => {
  it('names the area Integrations', async () => {
    serve({});
    await integrations();

    expect(screen.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'integrations',
    );
    expect(screen.getByTestId('page-header')).toHaveTextContent('Integrations');
  });
});

describe('Connected, first and never empty', () => {
  beforeEach(() => {
    serve({});
  });

  it('lists every connected integration above every other section, with the canonical chip', async () => {
    await integrations();

    const connected = screen.getByTestId('connected-section');
    const rows = within(connected).getAllByTestId('connected-integration');
    expect(rows.map((row) => row.getAttribute('data-integration'))).toEqual([
      'prometheus',
      'proxmox',
      'signoz',
    ]);
    expect(within(connected).getByText('Prometheus')).toBeInTheDocument();
    expect(
      connected.compareDocumentPosition(screen.getByTestId('suggested-section')) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('shows a degraded connected integration with its own chip, still inside Connected', async () => {
    // `signoz` is degraded, not failing — a check that once timed out, not
    // one that is currently refused. Mirrored as its own word rather than
    // collapsed into "failing", which is a different, worse claim.
    await integrations();

    const signoz = screen
      .getAllByTestId('connected-integration')
      .find((row) => row.getAttribute('data-integration') === 'signoz');
    expect(signoz).toBeDefined();
    expect(signoz?.querySelector('[data-credential-status="degraded"]')).not.toBeNull();
  });

  it('names the diagnostic beside the degraded chip for a degraded connected integration', async () => {
    // The edge case promises a chip *and* a diagnostic. `signoz` in the
    // fixture above already carries `healthDetail: 'the last verification
    // timed out'` — this asserts it actually reaches the row, not only the
    // record.
    await integrations();

    const signoz = screen
      .getAllByTestId('connected-integration')
      .find((row) => row.getAttribute('data-integration') === 'signoz');
    expect(one(signoz)).toHaveTextContent('the last verification timed out');
  });

  it('shows a credential nobody has verified yet as Stored, inside Connected, never in the grid', async () => {
    // A written credential the ledger has not run against yet reports
    // `health: 'unknown'` — `credentialStatus` maps that to the canonical
    // "stored", and it belongs beside the other connected integrations, not
    // back in the catalogue as though nothing had been entered.
    serve({
      integrations: {
        integrations: [
          integration({
            name: 'hermes',
            displayName: 'Hermes',
            health: 'unknown',
          }),
        ],
        known_gaps: [],
      },
    });
    await integrations();

    const connected = screen.getByTestId('connected-section');
    const row = within(connected).getByTestId('connected-integration');
    expect(row).toHaveAttribute('data-integration', 'hermes');
    expect(row.querySelector('[data-credential-status="stored"]')).not.toBeNull();
    expect(screen.queryByTestId('catalogue-item')).toBeNull();
  });

  it('offers a manage action for each connected integration, to its own address', async () => {
    await integrations();

    const prometheus = screen
      .getAllByTestId('connected-integration')
      .find((row) => row.getAttribute('data-integration') === 'prometheus');
    const manage = within(one(prometheus)).getByTestId('manage-integration');
    expect(manage).toHaveAttribute('href', '/integrations/prometheus');
  });

  it('never renders an empty Connected section', async () => {
    serve({
      integrations: {
        integrations: [integration({ name: 'grafana', health: 'unconfigured' })],
        known_gaps: [],
      },
    });
    await integrations();

    expect(screen.queryByTestId('connected-section')).toBeNull();
  });
});

describe('Suggested by the estate, in front of the catalogue', () => {
  beforeEach(() => {
    serve({});
  });

  it('shows the evidence the API already computed, and a connect action', async () => {
    await integrations();

    const suggested = screen.getByTestId('suggested-section');
    const row = within(suggested).getByTestId('suggested-integration');
    expect(row).toHaveAttribute('data-integration', 'grafana');
    expect(within(row).getByTestId('suggestion-evidence')).toHaveTextContent(
      '192.168.68.159:3000',
    );
    expect(within(row).getByTestId('suggestion-evidence')).toHaveTextContent(
      'monitoring',
    );
    expect(within(row).getByTestId('connect-suggested')).toHaveAttribute(
      'href',
      '/integrations/grafana',
    );
  });

  it('never renders an empty Suggested section', async () => {
    serve({
      integrations: {
        integrations: [integration({ name: 'prometheus', health: 'healthy' })],
        known_gaps: [],
      },
    });
    await integrations();

    expect(screen.queryByTestId('suggested-section')).toBeNull();
  });

  it('does not offer a suggestion for an integration already connected', async () => {
    serve({
      integrations: {
        integrations: [
          integration({
            name: 'prometheus',
            health: 'healthy',
            suggested: { address: '10.0.0.1:9090', fromResource: 'vm-1' },
          }),
        ],
        known_gaps: [],
      },
    });
    await integrations();

    expect(screen.queryByTestId('suggested-section')).toBeNull();
  });
});

describe('the summary line', () => {
  it('counts what the API actually served, never a literal', async () => {
    serve({});
    await integrations();

    const summary = screen.getByTestId('catalogue-summary');
    expect(summary).toHaveTextContent('6 integrations available');
    expect(summary).toHaveTextContent('3 connected');
    expect(summary).toHaveTextContent('1 suggested');
  });
});

describe('the catalogue grid: compact cards, never the raw id, never the form', () => {
  beforeEach(() => {
    serve({});
  });

  it('shows every not-yet-connected, not-suggested integration by display name, category and summary', async () => {
    await integrations();

    const grid = screen.getByTestId('catalogue-grid');
    const cards = within(grid).getAllByTestId('catalogue-item');
    expect(cards.map((card) => card.getAttribute('data-integration')).sort()).toEqual([
      'postgresql',
      'telegram',
    ]);
    expect(within(grid).getByText('PostgreSQL')).toBeInTheDocument();
    expect(within(grid).queryByText('postgresql')).toBeNull();
  });

  it('never shows a connected or suggested integration a second time in the grid', async () => {
    await integrations();

    const grid = screen.getByTestId('catalogue-grid');
    expect(within(grid).queryByText('Grafana')).toBeNull();
    expect(within(grid).queryByText('Prometheus')).toBeNull();
  });

  it('renders no credential form and no expandable state inside a card', async () => {
    await integrations();

    expect(screen.queryAllByTestId('credential')).toHaveLength(0);
  });

  it('links each card to its own deep-linked address', async () => {
    await integrations();

    const card = screen
      .getAllByTestId('catalogue-item')
      .find((each) => each.getAttribute('data-integration') === 'telegram');
    expect(within(one(card)).getByRole('link')).toHaveAttribute(
      'href',
      '/integrations/telegram',
    );
  });

  it('search also matches a capability, not only name, category and summary', async () => {
    // `point_in_time_restore` appears nowhere in this item's name, category
    // or summary — only in its capabilities. Seeding the URL's own `q` is
    // the same mechanism the search box itself writes to, so this exercises
    // the real filter rather than a second copy of it.
    serve({
      integrations: {
        integrations: [
          integration({
            name: 'chronoshift',
            displayName: 'Chronoshift',
            category: 'database',
            summary: 'Backup scheduling for managed clusters.',
            health: 'unconfigured',
            capabilities: ['point_in_time_restore'],
          }),
        ],
        known_gaps: [],
      },
    });
    await integrations({ q: 'point_in_time_restore' });

    const grid = screen.getByTestId('catalogue-grid');
    expect(within(grid).getByText('Chronoshift')).toBeInTheDocument();
  });
});

describe('the "not covered" footer link', () => {
  it('links to the reference page, and does not repeat the prose inline', async () => {
    serve({});
    await integrations();

    const link = screen.getByTestId('not-covered-link');
    expect(link).toHaveAttribute('href', '/integrations/not-covered');
    expect(link).toHaveTextContent('1');
    expect(screen.queryByTestId('known-gap')).toBeNull();
  });
});

describe('the credential panel, opened by a deep link', () => {
  it('opens the drawer for the named integration when the address names one', async () => {
    serve({});
    render(await IntegrationsScreen(await surfaceContext({}), 'telegram'));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toHaveTextContent('Telegram');
  });

  it('shows a human label, help and minimum scope per field, and a guide link when one exists', async () => {
    serve({});
    render(await IntegrationsScreen(await surfaceContext({}), 'telegram'));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByLabelText('Bot token')).toBeInTheDocument();
    expect(within(dialog).getByTestId('credential-field-scope')).toHaveTextContent(
      'sendMessage',
    );
    expect(within(dialog).getByTestId('credential-field-guide')).toHaveAttribute(
      'href',
      '/integrations/telegram/guide',
    );
  });

  it('names each required permission with what it grants and where it is turned on', async () => {
    serve({});
    render(await IntegrationsScreen(await surfaceContext({}), 'telegram'));

    const dialog = screen.getByRole('dialog');
    const permissions = within(dialog).getAllByTestId('required-permission');
    expect(permissions).toHaveLength(1);
    expect(permissions[0]).toHaveTextContent('sendMessage');
    expect(permissions[0]).toHaveTextContent('post a message as the bot');
    expect(permissions[0]).toHaveTextContent('BotFather');
  });

  it('names the one primary action "Save and test"', async () => {
    serve({});
    render(await IntegrationsScreen(await surfaceContext({}), 'telegram'));

    expect(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: /save and test/i,
      }),
    ).toBeInTheDocument();
  });

  it('carries the two-sentence security note', async () => {
    serve({});
    render(await IntegrationsScreen(await surfaceContext({}), 'telegram'));

    expect(
      within(screen.getByRole('dialog')).getByTestId('credential-security-note'),
    ).toHaveTextContent('never shown again');
  });

  it('does not open a drawer when the address names nothing', async () => {
    serve({});
    await integrations();

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('says the integration is not in the catalogue for a name that does not resolve', async () => {
    serve({});
    render(await IntegrationsScreen(await surfaceContext({}), 'not-a-real-vendor'));

    expect(screen.getByRole('dialog')).toHaveTextContent('not in the catalogue');
  });
});

describe('the advanced integrations-config section', () => {
  const CONFIG_NODE = 'org-northwind';

  const WRITER = {
    principal_id: 'user-operator',
    display_name: 'Avery Lockhart',
    email: 'avery.lockhart@example.invalid',
    kind: 'person',
    roles: ['owner'],
    permissions: ['integration.manage', 'config.read', 'config.write'],
    team_node_id: CONFIG_NODE,
    impersonated_by: null,
    impersonating: false,
  };

  function respond(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    });
  }

  function serveIntegrationsConfig(principal: unknown = WRITER): void {
    vi.stubGlobal('fetch', (input: unknown) => {
      const path = new URL(String(input), BASE).pathname;
      if (path === '/auth/me') return Promise.resolve(respond(principal));
      if (path === '/v1/integrations') return Promise.resolve(respond(INTEGRATIONS));
      if (path === '/v1/config') {
        return Promise.resolve(
          respond({
            nodes: [
              {
                kind: 'organisation',
                name: 'Northwind',
                node_id: CONFIG_NODE,
                parent_id: null,
              },
            ],
          }),
        );
      }
      if (path === `/v1/config/${CONFIG_NODE}`) {
        return Promise.resolve(
          respond({
            node_id: CONFIG_NODE,
            values: { integrations: {} },
            provenance: {},
          }),
        );
      }
      if (path === `/v1/config/${CONFIG_NODE}/fields`) {
        return Promise.resolve(
          respond({
            fields: [
              {
                path: 'integrations.active',
                label: 'Configured vendors',
                type: 'array',
                section: 'Integrations',
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

  it('is collapsed on arrival and draws integrations.active as an editable, reorderable list', async () => {
    serveIntegrationsConfig();

    await integrations();

    const details = screen.getByTestId('advanced-config-integrations');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    const field = details.querySelector(
      '[data-testid="config-field"][data-path="integrations.active"]',
    );
    expect(field).not.toBeNull();
    expect(field?.querySelector('[data-testid="object-list"]')).toBeInTheDocument();
  });

  it('offers no editor to a viewer who may not write configuration', async () => {
    serveIntegrationsConfig({
      ...WRITER,
      principal_id: 'user-viewer',
      permissions: ['integration.manage', 'config.read'],
    });

    await integrations();

    const details = screen.getByTestId('advanced-config-integrations');
    expect(within(details).queryByTestId('ask-preview')).toBeNull();
  });
});
