import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ResourcesScreen } from '@/surfaces/screens/resources';

/**
 * The list itself: a health bar that adds up, a name a reader can actually
 * search for, and the two divergence findings the estate reports in either
 * direction.
 *
 * This file replaces one written against the flat sortable table this
 * feature's own FR-007 retires — `columnheader`/`cell` roles, a utilisation
 * column, a divergence mark of its own column, none of which the card grid
 * has, by the artboard's own design. What is preserved is the underlying
 * behaviour: filtering by name and by health, the setup-return banner, the
 * absent/watched arithmetic, and the two panels a diverging resource still
 * reaches (`departed`, and the new `undeclared` this feature adds so the
 * "the provider reports it and the inventory does not" finding is not lost
 * along with the column that used to mark it).
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

const PRINCIPAL = {
  principal_id: 'user-operator',
  display_name: 'Avery Lockhart',
  kind: 'person',
  roles: ['owner'],
  permissions: ['investigation.read', 'config.read'],
  team_node_id: 'org-northwind',
  impersonating: false,
  impersonated_by: null,
};

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

interface ServeOptions {
  readonly resources: readonly unknown[];
  readonly summary?: unknown;
  readonly divergences?: readonly unknown[];
}

/** Answer the estate endpoints this screen reads, with a shape the test chose. */
function serve({
  resources,
  summary = { total: resources.length, captured_at: '2026-08-07T12:00:00Z' },
  divergences = [],
}: ServeOptions): void {
  const bodies: Record<string, unknown> = {
    '/auth/me': PRINCIPAL,
    '/v1/estate/resources': { resources },
    '/v1/estate/summary': summary,
    '/v1/estate/discovery/report': {
      reports: divergences.length === 0 ? [] : [{ divergences }],
    },
    '/v1/estate/unresolved-alert-targets': { targets: [] },
  };
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const body = bodies[path];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === undefined ? 404 : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

async function resources(query: Record<string, string> = {}): Promise<void> {
  render(await ResourcesScreen(await surfaceContext(query)));
}

/** `serve`, with the setup checklist answering `complete` rather than 404. */
function serveWithChecklist(complete: boolean): void {
  serve({ resources: [ALPHA] });
  const scenario = global.fetch;
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/v1/setup/checklist') {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            complete,
            provider: complete ? 'verified' : 'absent',
            integrations: [],
            steps: [
              {
                name: 'model-provider',
                state: complete ? 'done' : 'ready',
              },
            ],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    }
    return scenario(input as Parameters<typeof fetch>[0]);
  });
}

/** The card whose name (case-sensitive, as displayed) is `name`. */
function resourceCard(name: string): HTMLElement {
  const found = screen
    .getAllByTestId('resource-card')
    .find(
      (card) =>
        card.querySelector('[data-testid="resource-card-name"]')?.textContent === name,
    );
  if (found === undefined) throw new Error(`no card named ${name}`);
  return found;
}

const ALPHA = {
  resource_id: 'r-alpha',
  display_name: 'alpha',
  kind: 'container',
  health: 'healthy',
  correlation_key: 'ck-alpha',
  parent_id: 'node-1',
  parent_name: 'pve01',
  last_seen_at: '2026-08-07T12:00:00Z',
  attributes: { zone: 'dmz', criticality: 'critical' },
};

const BRAVO = {
  resource_id: 'r-bravo',
  display_name: 'bravo',
  kind: 'container',
  health: 'degraded',
  correlation_key: 'ck-bravo',
  parent_id: 'node-1',
  parent_name: 'pve01',
  last_seen_at: '2026-08-07T12:00:00Z',
  attributes: { zone: 'dmz', criticality: 'low' },
};

const CHARLIE = {
  resource_id: 'r-charlie',
  display_name: 'charlie',
  kind: 'container',
  health: 'unhealthy',
  correlation_key: 'ck-charlie',
  parent_id: 'node-1',
  parent_name: 'pve01',
  last_seen_at: '2026-08-07T12:00:00Z',
  attributes: { zone: 'core', criticality: 'critical' },
};

describe('resources: the card as the board draws it', () => {
  const CARD = {
    resource_id: 'res-1',
    display_name: 'runner-orchestrator',
    kind: 'container',
    health: 'unhealthy',
    last_seen_at: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
    unhealthy_since: new Date(Date.now() - 2 * 24 * 3600 * 1000).toISOString(),
    parent_id: 'node-pve01',
    parent_name: 'pve01',
  };

  it('says the out-duration through the shared formatter, never a calendar adverb', async () => {
    serve({ resources: [CARD] });
    await resources();

    const out = screen.getByTestId('resource-unhealthy-duration');
    // "2d out", not "the day before yesterday out": the `X fora` pattern
    // takes a duration, and only a duration.
    expect(out.textContent).toMatch(/2\s?d/);
    expect(out.textContent).not.toMatch(/yesterday|anteontem|ontem/i);
  });

  it('leads with the kind glyph and keeps the meta on one truncating line', async () => {
    serve({ resources: [CARD] });
    await resources();

    const card = resourceCard('runner-orchestrator');
    expect(card.querySelector('svg')).not.toBeNull();
    const meta = card.querySelector('.truncate:not([data-testid])');
    expect(meta?.textContent).toContain('Container');
  });
});

describe('resources: worst first is a view, carried in the address', () => {
  const cardOf = (id: string, health: string): unknown => ({
    resource_id: id,
    display_name: id,
    kind: 'container',
    health,
    last_seen_at: new Date().toISOString(),
    parent_id: 'node-pve01',
    parent_name: 'pve01',
  });

  it('offers the chip beside the type filters, linking the ordering into the address', async () => {
    serve({ resources: [cardOf('a-ok', 'healthy'), cardOf('b-bad', 'degraded')] });
    await resources();

    const chip = screen.getByTestId('order-worst-chip');
    expect(chip.getAttribute('href')).toContain('order=worst');
    expect(chip).toHaveAttribute('aria-pressed', 'false');
  });

  it('orders the whole health scale worse-first when the address says so', async () => {
    serve({
      resources: [
        cardOf('a-ok', 'healthy'),
        cardOf('b-stale', 'stale'),
        cardOf('c-degraded', 'degraded'),
      ],
    });
    await resources({ order: 'worst' });

    const names = screen
      .getAllByTestId('resource-card-name')
      .map((name) => name.textContent);
    expect(names).toEqual(['c-degraded', 'b-stale', 'a-ok']);
    expect(screen.getByTestId('order-worst-chip')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});

describe('resources: the two divergence findings', () => {
  it('surfaces what the provider reports and the inventory does not, in its own panel', async () => {
    serve({
      resources: [ALPHA, BRAVO],
      divergences: [{ kind: 'only_in_provider', subject: 'ck-alpha' }],
    });
    await resources();

    const panel = screen.getByTestId('undeclared');
    expect(within(panel).getByTestId('undeclared-entry')).toHaveTextContent('ck-alpha');
    // The card grid carries no per-card divergence mark any more -- the
    // artboard's card has no room for one -- so the name cell stays plain.
    expect(resourceCard('alpha')).not.toHaveTextContent(/inventory/i);
  });

  it('draws no undeclared panel at all when the last sweep found none', async () => {
    serve({ resources: [ALPHA, BRAVO] });
    await resources();

    expect(screen.queryByTestId('undeclared')).toBeNull();
  });
});

describe('resources: a filter by name', () => {
  it('narrows the grid to resources whose name matches, case-insensitively', async () => {
    serve({ resources: [ALPHA, BRAVO] });
    await resources({ q: 'BRA' });

    expect(screen.getAllByTestId('resource-card')).toHaveLength(1);
    expect(resourceCard('bravo')).toBeInTheDocument();
  });

  it('carries the typed name back into the search field', async () => {
    serve({ resources: [ALPHA, BRAVO] });
    await resources({ q: 'alpha' });

    expect(screen.getByRole('searchbox')).toHaveValue('alpha');
  });

  it('is a plain address-driven form, so a filter already chosen is not lost', async () => {
    serve({ resources: [ALPHA, BRAVO] });
    await resources({ criticality: 'critical' });

    const form = screen.getByTestId('resource-search');
    expect(form).toHaveAttribute('method', 'get');
  });
});

describe('resources: a filter by health', () => {
  it('applies the healthy value carried by the dashboard drill-down', async () => {
    serve({ resources: [ALPHA, BRAVO, CHARLIE] });
    await resources({ health: 'healthy' });

    const cards = screen.getAllByTestId('resource-card');
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveAttribute('data-health', 'healthy');
  });

  it('groups degraded and unhealthy resources under the problem drill-down', async () => {
    serve({ resources: [ALPHA, BRAVO, CHARLIE] });
    await resources({ health: 'problem' });

    const cards = screen.getAllByTestId('resource-card');
    expect(cards).toHaveLength(2);
    expect(screen.getByText('bravo')).toBeInTheDocument();
    expect(screen.getByText('charlie')).toBeInTheDocument();
    expect(screen.queryByText('alpha')).toBeNull();
  });
});

describe('resources: the way back to the wizard', () => {
  it('offers it when the wizard sent the operator here and setup is not finished', async () => {
    serveWithChecklist(false);
    await resources({ return: 'setup' });

    const link = screen.getByTestId('setup-return-link');
    expect(link).toHaveAttribute('href', '/first-run?step=provider');
  });

  it('says nothing when the address did not ask for it', async () => {
    serveWithChecklist(false);
    await resources();

    expect(screen.queryByTestId('setup-return-banner')).toBeNull();
  });

  it('says nothing once setup is already finished, even though the address asked', async () => {
    serveWithChecklist(true);
    await resources({ return: 'setup' });

    expect(screen.queryByTestId('setup-return-banner')).toBeNull();
  });
});

/**
 * The estate counts absent resources and then leaves them out of its total.
 *
 * `summarise` counts an absent resource into `by_health` and `continue`s
 * before adding it to `total` -- "watched" means what this estate currently
 * has rather than what it once had.
 */
describe('resources: what is watched, and what is merely remembered', () => {
  it('names the watched total once, distinct from the absent segment', async () => {
    serve({
      resources: [ALPHA, BRAVO],
      summary: {
        total: 96,
        by_health: { healthy: 75, absent: 5, unknown: 8, unhealthy: 13 },
        problems: 13,
        captured_at: '2026-08-07T12:00:00Z',
      },
    });
    await resources();

    expect(screen.getByTestId('health-watched')).toHaveTextContent('96');
    const legend = screen.getAllByTestId('health-legend-item');
    expect(
      legend.find((item) => item.getAttribute('data-health') === 'absent'),
    ).toHaveTextContent('5');
  });
});
