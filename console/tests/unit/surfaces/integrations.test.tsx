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
  readonly suggested?: {
    readonly address: string;
    readonly fromResource: string;
    // Required, like the API's own `resource_kind` — a suggestion the estate
    // produced always names a kind, resolved or not.
    readonly resourceKind: string;
    readonly resourceLabel?: string;
  };
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
            resource_label: source.suggested.resourceLabel ?? '',
            resource_kind: source.suggested.resourceKind,
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
      suggested: {
        address: '192.168.68.159:3000',
        fromResource: 'monitoring',
        resourceLabel: 'observability-01',
        resourceKind: 'guest',
      },
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
    // The resource's own legible name, read from `resource_label` — never the
    // raw identifier the estate matched on.
    expect(within(row).getByTestId('suggestion-evidence')).toHaveTextContent(
      'observability-01',
    );
    expect(within(row).getByTestId('connect-suggested')).toHaveAttribute(
      'href',
      '/integrations/grafana',
    );
  });

  it('never names the resource by its raw identifier, in the evidence or the link', async () => {
    await integrations();

    const suggested = screen.getByTestId('suggested-section');
    const row = within(suggested).getByTestId('suggested-integration');
    expect(within(row).getByTestId('suggestion-evidence')).not.toHaveTextContent(
      'monitoring',
    );
    expect(within(row).getByTestId('connect-suggested')).not.toHaveAttribute(
      'href',
      expect.stringContaining('monitoring'),
    );
  });

  it('keeps the raw resource identifier recoverable as a data attribute', async () => {
    await integrations();

    const suggested = screen.getByTestId('suggested-section');
    const row = within(suggested).getByTestId('suggested-integration');
    expect(row).toHaveAttribute('data-resource', 'monitoring');
  });

  it('names a resource address and kind, never a blank label, when the estate never resolved a name', async () => {
    serve({
      integrations: {
        integrations: [
          integration({
            name: 'redis',
            health: 'unconfigured',
            suggested: {
              address: '10.20.0.187:6379',
              fromResource: 'ct-9042',
              resourceKind: 'container',
              // `resourceLabel` deliberately omitted — the unresolvable case.
            },
          }),
        ],
        known_gaps: [],
      },
    });
    await integrations();

    const suggested = screen.getByTestId('suggested-section');
    const row = within(suggested).getByTestId('suggested-integration');
    const evidence = within(row).getByTestId('suggestion-evidence');
    expect(evidence).toHaveTextContent('10.20.0.187:6379');
    expect(evidence).toHaveTextContent('container');
    expect(evidence).not.toHaveTextContent('ct-9042');
    expect(row).toHaveAttribute('data-resource', 'ct-9042');
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
            suggested: {
              address: '10.0.0.1:9090',
              fromResource: 'vm-1',
              resourceLabel: 'prom-host',
              resourceKind: 'guest',
            },
          }),
        ],
        known_gaps: [],
      },
    });
    await integrations();

    expect(screen.queryByTestId('suggested-section')).toBeNull();
  });
});

describe('the three sections, always in this order, each absent rather than empty', () => {
  it('draws Connected, then Suggested by your estate, then Available, with Available carrying its own heading', async () => {
    serve({});
    await integrations();

    const connectedSection = screen.getByTestId('connected-section');
    const suggestedSection = screen.getByTestId('suggested-section');
    const availableHeading = screen.getByRole('heading', { name: 'Available' });
    const grid = screen.getByTestId('catalogue-grid');

    expect(
      connectedSection.compareDocumentPosition(suggestedSection) &
        Node.DOCUMENT_POSITION_FOLLOWING,
      'suggested-section is expected to follow connected-section',
    ).toBeTruthy();
    expect(
      suggestedSection.compareDocumentPosition(availableHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
      'the "Available" heading is expected to follow suggested-section',
    ).toBeTruthy();
    expect(
      availableHeading.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING,
      'catalogue-grid is expected to follow the "Available" heading',
    ).toBeTruthy();
  });

  it('never renders an empty Available section, when every integration is already Connected or Suggested', async () => {
    serve({
      integrations: {
        integrations: [
          integration({ name: 'prometheus', health: 'healthy' }),
          integration({
            name: 'grafana',
            health: 'unconfigured',
            suggested: {
              address: '192.168.68.159:3000',
              fromResource: 'monitoring',
              resourceLabel: 'observability-01',
              resourceKind: 'guest',
            },
          }),
        ],
        known_gaps: [],
      },
    });
    await integrations();

    expect(screen.getByTestId('connected-section')).toBeInTheDocument();
    expect(screen.getByTestId('suggested-section')).toBeInTheDocument();
    expect(screen.queryByTestId('available-section')).toBeNull();
    expect(screen.queryByTestId('catalogue-grid')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Available' })).toBeNull();
  });
});

describe('the counts this screen shows', () => {
  it('counts what the API actually served, never a literal', async () => {
    serve({});
    await integrations();

    // In the page header's strip, where every other screen keeps its counts.
    const strip = screen.getByTestId('count-strip');
    expect(within(strip).getByTestId('count-total')).toHaveTextContent('6');
    expect(strip).toHaveTextContent('3');
    expect(strip).toHaveTextContent(/connected/i);
    // And they add up, which is the property the strip exists to hold.
    expect(strip).toHaveAttribute('data-balanced', 'true');
  });

  it('says what only it can say, and nothing when there is none of it', async () => {
    serve({});
    await integrations();

    // The one fact a count cannot carry: the estate found these running.
    const summary = screen.getByTestId('catalogue-summary');
    expect(summary).toHaveTextContent('1');
    expect(summary.textContent).toMatch(/already running/i);
  });

  it('drops the sentence entirely rather than saying none were suggested', async () => {
    serve({
      integrations: {
        integrations: [
          integration({ name: 'prometheus', health: 'healthy' }),
          integration({ name: 'postgresql', health: 'unconfigured' }),
        ],
        known_gaps: [],
      },
    });
    await integrations();

    // Not "0 suggested", and not the word at all — absent, never a zero
    // standing in for it. The header's strip still carries the two counts.
    expect(screen.queryByTestId('catalogue-summary')).toBeNull();
    const strip = screen.getByTestId('count-strip');
    expect(within(strip).getByTestId('count-total')).toHaveTextContent('2');
  });
});
