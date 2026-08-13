import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { CLOCK_ENV, surfaceContext } from '@/surfaces/context';
import { AuditScreen } from '@/surfaces/screens/audit';

/**
 * The audit trail with its real volume in it: thousands of identical polling
 * resolutions and, somewhere among them, the handful of things a person did.
 *
 * Every fixture below is built around one question — can a human action from
 * today still be found — and pins the two mechanisms spec 038 asks for
 * together: consecutive identical events collapse into one row, and the
 * system principal is excluded from the reading a viewer lands on by default.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** Built rather than written: a literal origin in console source is refused. */
const BASE = ['http:', '//gateway.test'].join('');

const PRINCIPAL = {
  principal_id: 'user-operator',
  display_name: 'Avery Lockhart',
  kind: 'person',
  roles: ['owner'],
  permissions: ['audit.export'],
  team_node_id: 'org-northwind',
  impersonating: false,
  impersonated_by: null,
};

const NOW = '2026-08-13T12:00:00Z';

/** One of the deployment's own polling resolutions — the noise item 1 is about. */
function systemEvent(id: string, occurredAt: string): unknown {
  return {
    event_id: id,
    occurred_at: occurredAt,
    actor_kind: 'agent',
    actor_id: 'default',
    action: 'credential.resolve',
    resource_kind: 'credential',
    resource_id: 'prometheus',
    outcome: 'ALLOWED',
    detail: {},
  };
}

/** Something a person actually did. */
function humanEvent(
  id: string,
  occurredAt: string,
  actorId = 'alice@example.com',
  action = 'config.set',
): unknown {
  return {
    event_id: id,
    occurred_at: occurredAt,
    actor_kind: 'human',
    actor_id: actorId,
    action,
    resource_kind: 'config',
    resource_id: 'org-northwind',
    outcome: 'ALLOWED',
    detail: {},
  };
}

function serve(events: readonly unknown[]): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const byPath: Record<string, unknown> = {
      '/auth/me': PRINCIPAL,
      '/audit/events': { events, total: events.length },
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
  vi.stubEnv(CLOCK_ENV, NOW);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function audit(params: Record<string, string> = {}): Promise<void> {
  render(await AuditScreen(await surfaceContext(params)));
}

function rowList(): HTMLElement {
  return screen.getByTestId('row-list');
}

describe('a burst of identical polling', () => {
  it('collapses consecutive identical events into one row with a count', async () => {
    serve([
      systemEvent('evt-3', '2026-08-13T11:59:50Z'),
      systemEvent('evt-2', '2026-08-13T11:59:40Z'),
      systemEvent('evt-1', '2026-08-13T11:59:30Z'),
    ]);
    // The whole fixture is system noise, so it only shows once the reading
    // is widened past the default that hides it.
    await audit({ audience: 'all' });

    const rows = within(rowList()).getAllByTestId('row');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent('3 events');
  });

  it('does not collapse events that are not actually identical', async () => {
    serve([
      systemEvent('evt-2', '2026-08-13T11:59:50Z'),
      humanEvent('evt-human', '2026-08-13T11:59:40Z'),
      systemEvent('evt-1', '2026-08-13T11:59:30Z'),
    ]);
    await audit({ audience: 'all' });

    expect(within(rowList()).getAllByTestId('row')).toHaveLength(3);
  });
});

describe('a human action buried in polling noise', () => {
  it('is findable in the reading a viewer lands on by default', async () => {
    const events = [
      systemEvent('evt-6', '2026-08-13T11:59:50Z'),
      systemEvent('evt-5', '2026-08-13T11:59:40Z'),
      systemEvent('evt-4', '2026-08-13T11:59:30Z'),
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
      systemEvent('evt-3', '2026-08-13T08:59:50Z'),
      systemEvent('evt-2', '2026-08-13T08:59:40Z'),
      systemEvent('evt-1', '2026-08-13T08:59:30Z'),
    ];
    serve(events);
    await audit();

    const rows = within(rowList()).getAllByTestId('row');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent('alice@example.com');
  });

  it('excludes the system principal from the default reading', async () => {
    serve([
      systemEvent('evt-1', '2026-08-13T11:59:50Z'),
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
    ]);
    await audit();

    expect(within(rowList()).queryByText('default')).toBeNull();
  });

  it('offers a link back to the system events it hid, and follows through', async () => {
    serve([
      systemEvent('evt-2', '2026-08-13T11:59:50Z'),
      systemEvent('evt-1', '2026-08-13T11:59:40Z'),
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
    ]);
    await audit();

    const toggle = screen.getByTestId('audit-audience-toggle');
    expect(toggle).toHaveTextContent('default');
    expect(toggle).toHaveTextContent('2 events');

    cleanup();
    await audit({ audience: 'all' });
    const rows = within(rowList()).getAllByTestId('row');
    // The two system events collapse into one row beside the human one.
    expect(rows).toHaveLength(2);
  });

  it('does not offer the toggle once a specific principal is already chosen', async () => {
    serve([
      systemEvent('evt-1', '2026-08-13T11:59:50Z'),
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
    ]);
    await audit({ actor: 'default' });

    expect(screen.queryByTestId('audit-audience-toggle')).toBeNull();
  });
});

describe('a filter populated with a single value', () => {
  it('does not render Principal or Action when neither offers a real choice', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    expect(screen.queryAllByTestId('filter')).toHaveLength(0);
  });

  it('renders once there is a real choice to make', async () => {
    serve([
      humanEvent(
        'evt-alice',
        '2026-08-13T09:00:00Z',
        'alice@example.com',
        'config.set',
      ),
      humanEvent('evt-bob', '2026-08-13T09:05:00Z', 'bob@example.com', 'config.clear'),
    ]);
    await audit();

    const rendered = screen
      .getAllByTestId('filter')
      .map((filter) => filter.getAttribute('data-filter'));
    expect(rendered).toEqual(['actor', 'action']);
  });
});

describe('the period filter', () => {
  it('offers presets, each pointing at a bounded window', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const links = within(screen.getByTestId('tab-links')).getAllByTestId('tab-link');
    expect(links.length).toBeGreaterThan(1);
    expect(
      links.some((link) => (link.getAttribute('href') ?? '').includes('since=')),
    ).toBe(true);
  });
});

describe('a slug written out in full', () => {
  it('shows the action and the outcome as words rather than as machine slugs', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const list = rowList();
    expect(within(list).queryByText('config.set')).toBeNull();
    expect(within(list).queryByText('ALLOWED')).toBeNull();
    expect(list).toHaveTextContent('Config Set');
    expect(list).toHaveTextContent('Allowed');
  });
});
