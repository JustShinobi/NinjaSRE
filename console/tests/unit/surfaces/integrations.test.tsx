import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { IntegrationsScreen } from '@/surfaces/screens/integrations';

/**
 * What the Catalogue's write half became: 85 credential forms on their own
 * address, each collapsed to its real state until asked for.
 *
 * Two things this file pins:
 *
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

function integration(source: {
  readonly name: string;
  readonly displayName?: string;
  readonly health: string;
  readonly healthDetail?: string;
}): unknown {
  return {
    name: source.name,
    display_name: source.displayName ?? source.name,
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
    integration({
      name: 'prometheus',
      displayName: 'Prometheus',
      health: 'unconfigured',
    }),
    integration({ name: 'datadog', displayName: 'Datadog', health: 'unknown' }),
    integration({
      name: 'chat',
      displayName: 'Team Chat',
      health: 'healthy',
      healthDetail: 'verified 3 hours ago',
    }),
    integration({
      name: 'ticketing',
      displayName: 'Ticketing Desk',
      health: 'degraded',
      healthDetail: 'the last verification timed out',
    }),
  ],
  known_gaps: [],
};

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

/** The collapsed card for one integration, by name. */
function integrationCard(name: string): HTMLElement {
  const found = screen
    .getAllByTestId('integration')
    .find((card) => card.getAttribute('data-integration') === name);
  if (found === undefined) throw new Error(`no integration card for ${name}`);
  return found;
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

describe('a credential form is collapsed until asked for', () => {
  beforeEach(() => {
    serve({});
  });

  it('shows every integration state without expanding anything', async () => {
    await integrations();

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
    expect(
      integrationCard('chat').querySelector('[data-credential-status="verified"]'),
    ).not.toBeNull();
    expect(
      within(integrationCard('chat')).getByText(/verified 3 hours ago/),
    ).toBeDefined();

    expect(integrationCard('ticketing').getAttribute('data-state')).toBe('degraded');
    expect(
      integrationCard('ticketing').querySelector('[data-credential-status="failing"]'),
    ).not.toBeNull();
  });

  it('titles every card with the display name, never the raw id', async () => {
    await integrations();

    expect(within(integrationCard('chat')).getByText('Team Chat')).toBeInTheDocument();
    expect(within(integrationCard('chat')).queryByText('chat')).toBeNull();
    expect(
      within(integrationCard('ticketing')).getByText('Ticketing Desk'),
    ).toBeInTheDocument();
  });

  it('renders no credential form and no verify control before anything is expanded', async () => {
    await integrations();

    expect(screen.queryAllByTestId('credential')).toHaveLength(0);
    expect(screen.queryAllByTestId('verify-row')).toHaveLength(0);
  });

  it('reveals the form and the verify control for one card, and only that one, once expanded', async () => {
    await integrations();

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

describe('a state filter, so eighty-five cards is a search rather than a scroll', () => {
  beforeEach(() => {
    serve({});
  });

  it('offers exactly the four states this dataset actually has, and nothing more', async () => {
    await integrations();

    const filter = screen.getByTestId('filter');
    expect(filter).toHaveAttribute('data-filter', 'state');
    const options = within(filter)
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(options).toEqual(['Any', 'Not connected', 'Stored', 'Verified', 'Failing']);
  });

  it('narrows the cards to the state named in the address', async () => {
    await integrations({ state: 'healthy' });

    expect(screen.getAllByTestId('integration')).toHaveLength(1);
    expect(integrationCard('chat')).toBeInTheDocument();
  });

  it('is silent about the state in the address once nothing else needs it', async () => {
    await integrations({ state: 'degraded' });

    expect(screen.getAllByTestId('integration')).toHaveLength(1);
    expect(integrationCard('ticketing')).toBeInTheDocument();
  });

  it('carries the whole set again once the filter is cleared', async () => {
    await integrations();

    expect(screen.getAllByTestId('integration')).toHaveLength(4);
  });
});
