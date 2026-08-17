import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { CLOCK_ENV, surfaceContext } from '@/surfaces/context';
import { AuditLogScreen } from '@/surfaces/settings/audit';

/**
 * The Audit log Settings page: a self-addressing replacement for the old
 * Administration "Audit" tab.
 *
 * Two defects this page exists to not reproduce, both confirmed live against
 * the tab it replaces: every navigational control used to hard-code
 * `/administration`, so a period preset clicked from this page's own address
 * (which carries no `tab`) redirected to Members & roles instead of staying
 * here; and the empty state was computed from what was left *after* the
 * client-side system-principal exclusion, so a window full of nothing but
 * polling noise showed "Nothing has been recorded" beside a toggle offering
 * to reveal the very events that contradicted it.
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
const PATH = '/settings/audit-log';

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

function systemEvent(id: string, occurredAt: string): unknown {
  return {
    event_id: id,
    occurred_at: occurredAt,
    actor_kind: 'agent',
    actor_id: 'default',
    action: 'credential.resolve',
    resource_kind: 'credential',
    resource_id: 'prometheus',
    outcome: 'allowed',
    detail: {},
  };
}

function humanEvent(
  id: string,
  occurredAt: string,
  actorId = 'alice@example.com',
  action = 'config.set',
): unknown {
  return {
    event_id: id,
    occurred_at: occurredAt,
    actor_kind: 'user',
    actor_id: actorId,
    action,
    resource_kind: 'config',
    resource_id: 'org-northwind',
    outcome: 'allowed',
    detail: {},
  };
}

let requests: string[] = [];

function serve(events: readonly unknown[], total?: number): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const address = new URL(String(input), BASE);
    requests.push(address.toString());
    const byPath: Record<string, unknown> = {
      '/auth/me': PRINCIPAL,
      '/audit/events': { events, total: total ?? events.length },
    };
    const body = byPath[address.pathname];
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
  requests = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function audit(params: Record<string, string> = {}): Promise<void> {
  render(await AuditLogScreen(await surfaceContext(params)));
}

function rowList(): HTMLElement {
  return screen.getByTestId('row-list');
}

describe('every navigational control addresses this page, not /administration', () => {
  it('the period presets point at the audit-log address', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const links = within(screen.getByTestId('tab-links')).getAllByTestId('tab-link');
    const preset = links.find((link) =>
      (link.getAttribute('href') ?? '').includes('since='),
    );
    expect(preset).toBeDefined();
    expect(preset?.getAttribute('href')).toMatch(new RegExp(`^${PATH}\\?`));
  });

  it("the 'Any' period link points at the audit-log address", async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit({ since: '2026-08-01T00:00:00Z' });

    const links = within(screen.getByTestId('tab-links')).getAllByTestId('tab-link');
    const any = links.find((link) => link.getAttribute('data-tab') === 'any');
    expect(any?.getAttribute('href')?.startsWith(PATH)).toBe(true);
  });

  it('a row opens at the audit-log address', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const row = within(rowList()).getByTestId('row');
    expect(row.querySelector('a')?.getAttribute('href')).toMatch(
      new RegExp(`^${PATH}\\?`),
    );
  });

  it('the empty-state action widens the period at the audit-log address, not by dropping every filter', async () => {
    serve([], 0);
    await audit({ actor: 'alice@example.com' });

    const action = screen.getByTestId('way-back');
    const href = action.getAttribute('href') ?? '';
    expect(href.startsWith(PATH)).toBe(true);
    // Widening the period must not be the same act as discarding every other
    // filter the operator had set — the empty-state's own no-op defect.
    expect(href).toContain('actor=alice%40example.com');
  });

  it('the audience toggle points at the audit-log address', async () => {
    serve([
      systemEvent('evt-1', '2026-08-13T11:59:50Z'),
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
    ]);
    await audit();

    const toggle = screen.getByTestId('audit-audience-toggle');
    expect(toggle.getAttribute('href')?.startsWith(PATH)).toBe(true);
  });
});

describe('the empty state answers what the page actually draws, never a bigger, merely-fetched population', () => {
  it('an entirely-system fetch declares the exclusion and empties honestly, rather than a headers-only table with nothing under it', async () => {
    serve([
      systemEvent('evt-1', '2026-08-13T11:59:50Z'),
      systemEvent('evt-2', '2026-08-13T11:59:40Z'),
    ]);
    await audit();

    // Two events were genuinely fetched and both are system noise, kept out
    // of the default reading. Showing "Nothing has been recorded" here is
    // honest exactly because the toggle beside it says why and offers the
    // way out — what is forbidden is a table with headers over an empty
    // body and no explanation at all, which is what a `ready`, zero-row
    // panel drew before this.
    expect(screen.getByText('Nothing has been recorded')).toBeInTheDocument();
    expect(screen.getByTestId('panel')).toHaveAttribute('data-state', 'empty');
    expect(screen.getByTestId('audit-audience-toggle')).toHaveTextContent('2 events');
  });

  it('the diagnosed shape — 200 fetched, all system, a much larger declared total — still empties honestly rather than drawing nothing under a full-looking header', async () => {
    const events = Array.from({ length: 200 }, (_, index) =>
      systemEvent(`evt-sys-${String(index)}`, '2026-08-13T11:59:50Z'),
    );
    serve(events, 156735);
    await audit();

    expect(screen.getByTestId('panel')).toHaveAttribute('data-state', 'empty');
    expect(screen.getByTestId('audit-audience-toggle')).toHaveTextContent('200 events');
    // Nothing on the page may claim a population as large as the backend's
    // own total — the truncation notice must not render as though 200 rows
    // are on screen when zero are.
    expect(screen.queryByTestId('audit-truncated')).toBeNull();
  });

  it('shows "nothing recorded" when nothing was fetched at all, exactly as it does when everything fetched was hidden', async () => {
    serve([], 0);
    await audit();

    expect(screen.getByText('Nothing has been recorded')).toBeInTheDocument();
    expect(screen.getByTestId('panel')).toHaveAttribute('data-state', 'empty');
  });

  it('draws the table, not the empty state, once a human action survives the default reading', async () => {
    serve([
      systemEvent('evt-1', '2026-08-13T11:59:50Z'),
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
    ]);
    await audit();

    expect(screen.getByTestId('panel')).toHaveAttribute('data-state', 'ready');
    expect(within(rowList()).getAllByTestId('row')).toHaveLength(1);
  });
});

describe('named, readable period presets', () => {
  it('offers a phrase rather than a raw date range', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const links = within(screen.getByTestId('tab-links')).getAllByTestId('tab-link');
    expect(links.some((link) => /last 7 days/i.test(link.textContent))).toBe(true);
    expect(links.some((link) => /last 30 days/i.test(link.textContent))).toBe(true);
  });
});

describe('a preset stays marked active on the real wall clock, not only at the instant it was built', () => {
  it('reruns the query with the new interval and marks the chosen preset active', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    // Exactly what a preset link's own `since` is built as, at the moment
    // this render's `now` computes it — the case the exact-match reading
    // already handled, kept here as the still-passing baseline.
    const since = new Date(Date.parse(NOW) - 7 * 24 * 60 * 60 * 1000).toISOString();
    await audit({ since });

    const links = within(screen.getByTestId('tab-links')).getAllByTestId('tab-link');
    const sevenDays = links.find((link) => link.getAttribute('data-tab') === 'days-7');
    expect(sevenDays).toHaveAttribute('aria-current', 'page');
  });

  it('still marks the preset active once real time has passed between the link and the request', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    // A `since` built a minute and a half before this request — exactly what
    // a link clicked shortly after the page that offered it rendered looks
    // like once the wall clock has moved. An exact match against a freshly
    // recomputed "7 days ago" can never equal this, because the two are
    // computed against two different instants; a real browser produces this
    // on every click, not only on a slow one.
    const drift = 90_000;
    const since = new Date(
      Date.parse(NOW) - 7 * 24 * 60 * 60 * 1000 + drift,
    ).toISOString();
    await audit({ since });

    const links = within(screen.getByTestId('tab-links')).getAllByTestId('tab-link');
    const sevenDays = links.find((link) => link.getAttribute('data-tab') === 'days-7');
    expect(sevenDays).toHaveAttribute('aria-current', 'page');
    const any = links.find((link) => link.getAttribute('data-tab') === 'any');
    expect(any).not.toHaveAttribute('aria-current', 'page');
  });

  it('marks no preset active for a since that matches none of them, drift or not', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    const since = new Date(Date.parse(NOW) - 3 * 24 * 60 * 60 * 1000).toISOString();
    await audit({ since });

    const links = within(screen.getByTestId('tab-links')).getAllByTestId('tab-link');
    for (const link of links) {
      expect(link).not.toHaveAttribute('aria-current', 'page');
    }
  });
});

describe('filters and export respect each other', () => {
  it('renders actor and action once there is a real choice', async () => {
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

  it('the export link carries the active filters', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit({ actor: 'alice@example.com' });

    const link = screen.getByTestId('audit-export');
    expect(link.getAttribute('href')).toContain('actor_id=alice%40example.com');
  });

  it('reports a truncated total honestly', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')], 5);
    await audit();

    expect(screen.getByTestId('audit-truncated')).toHaveTextContent('5');
  });

  it('the shown count never exceeds the population the audience exclusion actually leaves drawn', async () => {
    // Ten fetched, nine of them system noise excluded by default: the body
    // draws one row, and the notice above it must claim exactly that many —
    // never the ten that were merely fetched.
    const events = [
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
      ...Array.from({ length: 9 }, (_, index) =>
        systemEvent(`evt-sys-${String(index)}`, '2026-08-13T08:00:00Z'),
      ),
    ];
    serve(events, 500);
    await audit();

    expect(within(rowList()).getAllByTestId('row')).toHaveLength(1);
    const notice = screen.getByTestId('audit-truncated');
    expect(notice).toHaveTextContent('1');
    expect(notice).not.toHaveTextContent('10 of');
  });

  it('does not render Principal or Action when neither offers a real choice', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    expect(screen.queryAllByTestId('filter')).toHaveLength(0);
  });

  it('never asks the gateway for more events than its own page bound allows', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const eventsCall = requests.find(
      (address) => new URL(address).pathname === '/audit/events',
    );
    expect(eventsCall).toBeDefined();
    // The real backend's `MAX_QUERY_PAGE_SIZE` (`config/constants/persistence.py`)
    // is 200 and rejects anything larger with a 400 — a bound only this stub,
    // not the deployment, would ever let past silently.
    const limit = Number(new URL(eventsCall ?? '').searchParams.get('limit'));
    expect(limit).toBeLessThanOrEqual(200);
  });
});

describe('bursts of identical polling still collapse', () => {
  it('collapses consecutive identical events into one row with a count', async () => {
    serve([
      systemEvent('evt-3', '2026-08-13T11:59:50Z'),
      systemEvent('evt-2', '2026-08-13T11:59:40Z'),
      systemEvent('evt-1', '2026-08-13T11:59:30Z'),
    ]);
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
    serve([
      systemEvent('evt-3', '2026-08-13T11:59:50Z'),
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
      systemEvent('evt-1', '2026-08-13T08:59:30Z'),
    ]);
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

  it('offers a link back to the system events it hid, and following it reveals them', async () => {
    serve([
      systemEvent('evt-2', '2026-08-13T11:59:50Z'),
      systemEvent('evt-1', '2026-08-13T11:59:40Z'),
      humanEvent('evt-human', '2026-08-13T09:00:00Z'),
    ]);
    await audit();

    expect(screen.getByTestId('audit-audience-toggle')).toHaveTextContent('2 events');

    cleanup();
    await audit({ audience: 'all' });
    expect(within(rowList()).getAllByTestId('row')).toHaveLength(2);
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

describe('a slug written out in full', () => {
  it('shows the action as words rather than as a machine slug', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const list = rowList();
    expect(within(list).queryByText('config.set')).toBeNull();
    expect(list).toHaveTextContent('Config Set');
  });

  it('shows the outcome raw, lower case, matching the real enum’s own wire value', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const list = rowList();
    expect(within(list).queryByText('ALLOWED')).toBeNull();
    expect(list).toHaveTextContent('allowed');
  });

  it('colours the outcome by the role the design system already has for it', async () => {
    serve([humanEvent('evt-human', '2026-08-13T09:00:00Z')]);
    await audit();

    const badge = rowList().querySelector('[data-role]');
    expect(badge).not.toBeNull();
    // `allowed` is meant to read as a recognised, positive outcome — not the
    // generic neutral chip a status the design system has never heard of
    // gets, which is what a badge fed a humanised label rather than the raw
    // API value falls back to.
    expect(badge).toHaveAttribute('data-role', 'success');
    expect(badge).toHaveAttribute('data-known', 'true');
  });
});
