import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ResourcesScreen } from '@/surfaces/screens/resources';

/**
 * The list itself: columns that earn their place, one health vocabulary, and
 * a name a reader can actually search for.
 *
 * Three defects lived here together. A column that read "Not recorded" on
 * every row taught the reader to stop looking at every column. A header that
 * called a number "degraded" when the endpoint's own breakdown said otherwise
 * was a second vocabulary for the same axis the badges already had one for.
 * And a suffix concatenated onto a resource's name was noise in the one cell
 * a reader actually reads — the name — rather than a fact with a column of
 * its own.
 *
 * A hand-built fetch stub rather than the committed dataset: each of these
 * needs a shape (an all-zero utilisation, a `by_health` that disagrees with
 * `problems`, a divergence) the committed capture does not carry, the same
 * way `resource-signals.test.tsx` stubs one for the pressure-key case.
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

function resourceRow(id: string): HTMLElement {
  const found = screen
    .getAllByTestId('row')
    .find((row) => row.getAttribute('data-row') === id);
  if (found === undefined) throw new Error(`no row for ${id}`);
  return found;
}

function columnIndex(header: string): number {
  const headers = screen.getAllByRole('columnheader').map((cell) => cell.textContent);
  const found = headers.findIndex((text) => text.includes(header));
  if (found === -1) throw new Error(`no column headed ${header}`);
  return found;
}

/** The cell at `column` in `row`, or a thrown error naming which one is missing. */
function cellAt(row: HTMLElement, column: number): HTMLElement {
  const found = within(row).getAllByRole('cell')[column];
  if (found === undefined) throw new Error(`no cell at column ${String(column)}`);
  return found;
}

function cellText(row: HTMLElement, column: number): string {
  return cellAt(row, column).textContent;
}

const ALPHA = {
  resource_id: 'r-alpha',
  display_name: 'alpha',
  kind: 'container',
  health: 'healthy',
  correlation_key: 'ck-alpha',
  last_seen_at: '2026-08-07T12:00:00Z',
  attributes: { zone: 'dmz', criticality: 'critical' },
};

const BRAVO = {
  resource_id: 'r-bravo',
  display_name: 'bravo',
  kind: 'container',
  health: 'degraded',
  correlation_key: 'ck-bravo',
  last_seen_at: '2026-08-07T12:00:00Z',
  attributes: { zone: 'dmz', criticality: 'low' },
};

const CHARLIE = {
  resource_id: 'r-charlie',
  display_name: 'charlie',
  kind: 'container',
  health: 'unhealthy',
  correlation_key: 'ck-charlie',
  last_seen_at: '2026-08-07T12:00:00Z',
  attributes: { zone: 'core', criticality: 'critical' },
};

describe('resources: no column reads "Not recorded" on every row', () => {
  it('draws no utilisation column when nothing in view has a reading', async () => {
    serve({ resources: [ALPHA, BRAVO] });
    await resources();

    expect(screen.queryByRole('columnheader', { name: /Utilisation/i })).toBeNull();
  });

  it('draws the utilisation column, meter and all, once something has a reading', async () => {
    serve({
      resources: [
        { ...ALPHA, attributes: { ...ALPHA.attributes, memory_percent: 40 } },
        BRAVO,
      ],
    });
    await resources();

    expect(
      screen.getByRole('columnheader', { name: /Utilisation/i }),
    ).toBeInTheDocument();
    const column = columnIndex('Utilisation');

    // Alpha has a reading: a meter, not a bar for a percentage of nothing.
    const alphaCell = cellAt(resourceRow('r-alpha'), column);
    expect(within(alphaCell).getByRole('progressbar')).toBeInTheDocument();

    // Bravo has none: the column exists, and says so plainly rather than
    // leaving the cell blank.
    expect(cellText(resourceRow('r-bravo'), column)).toMatch(/not recorded/i);
  });
});

describe('resources: one health vocabulary', () => {
  it('counts the header’s "degraded" against the same breakdown the badges use, not the combined problem count', async () => {
    serve({
      resources: [ALPHA, BRAVO],
      summary: {
        total: 10,
        by_health: { healthy: 6, degraded: 2, unhealthy: 2 },
        problems: 4,
        captured_at: '2026-08-07T12:00:00Z',
      },
    });
    await resources();

    const strip = screen.getByTestId('count-strip');
    // "degraded" is the breakdown's own degraded, never `problems` — which
    // folds degraded and unhealthy together and is what left this header
    // unable to be added up against the badges below it.
    const degraded = within(strip)
      .getAllByTestId('count-part')
      .find((part) => /degraded/i.test(part.textContent));
    expect(degraded).toHaveTextContent('2');
    expect(degraded).not.toHaveTextContent('4');
  });

  /**
   * The parts reach the whole, whatever states the deployment is in.
   *
   * The header shipped "97 watched · 76 healthy · 0 degraded · 13 unhealthy"
   * for a fortnight: three parts totalling 89, with the missing eight visible
   * in the table two hundred pixels below. Generated from the breakdown rather
   * than from a sentence with four holes, so a state nobody anticipated gets a
   * cell instead of vanishing.
   */
  it('adds up, including the states the old sentence had no room for', async () => {
    serve({
      resources: [ALPHA, BRAVO],
      summary: {
        total: 97,
        by_health: { healthy: 76, unhealthy: 13, unknown: 8 },
        problems: 13,
        captured_at: '2026-08-07T12:00:00Z',
      },
    });
    await resources();

    const strip = screen.getByTestId('count-strip');
    expect(strip).toHaveAttribute('data-balanced', 'true');
    expect(within(strip).getByTestId('count-total')).toHaveTextContent('97');
    expect(strip).toHaveTextContent(/unknown/i);
  });

  it('says what it cannot account for rather than quietly dropping it', async () => {
    serve({
      resources: [ALPHA, BRAVO],
      summary: {
        total: 97,
        by_health: { healthy: 76, unhealthy: 13 },
        problems: 13,
        captured_at: '2026-08-07T12:00:00Z',
      },
    });
    await resources();

    const strip = screen.getByTestId('count-strip');
    expect(strip).toHaveAttribute('data-balanced', 'false');
    expect(within(strip).getByTestId('count-shortfall')).toHaveTextContent('8');
  });
});

describe('resources: the divergence mark is its own column', () => {
  it('leaves the name cell carrying only the name', async () => {
    serve({
      resources: [ALPHA, BRAVO],
      divergences: [{ kind: 'only_in_provider', subject: 'ck-alpha' }],
    });
    await resources();

    const nameText = cellText(resourceRow('r-alpha'), 0);
    // The cell's link also carries a visually-hidden "Open" label for a
    // reader who hears only the link — real content, just not the name.
    expect(nameText.replace(/Open$/, '').trim()).toBe('alpha');
    expect(nameText).not.toMatch(/inventory/i);
  });

  it('marks the diverging resource in a column of its own, and says nothing for the rest', async () => {
    serve({
      resources: [ALPHA, BRAVO],
      divergences: [{ kind: 'only_in_provider', subject: 'ck-alpha' }],
    });
    await resources();

    const column = columnIndex('inventory');
    expect(cellText(resourceRow('r-alpha'), column)).toMatch(/inventory/i);
    expect(cellText(resourceRow('r-bravo'), column)).toMatch(/not recorded/i);
  });

  it('draws no divergence column at all when the last sweep found none', async () => {
    serve({ resources: [ALPHA, BRAVO] });
    await resources();

    expect(screen.queryByRole('columnheader', { name: /inventory/i })).toBeNull();
  });
});

describe('resources: unexplained jargon gets a tooltip and a way to fix it', () => {
  it('explains the divergence mark and what to do about it', async () => {
    serve({
      resources: [ALPHA, BRAVO],
      divergences: [{ kind: 'only_in_provider', subject: 'ck-alpha' }],
    });
    await resources();

    const column = columnIndex('inventory');
    const cell = cellAt(resourceRow('r-alpha'), column);
    expect(within(cell).getByTitle(/inventory/i)).toHaveTextContent(/inventory/i);
  });

  it('explains "Unplaced" and links to where a zone is declared', async () => {
    // A mixed estate: bravo is in a zone, alpha is not. The odd one out is the
    // finding, so it keeps its cell, its explanation and its way to fix it.
    serve({
      resources: [{ ...ALPHA, attributes: { criticality: 'critical' } }, BRAVO],
    });
    await resources();

    const column = columnIndex('Zone');
    const link = within(cellAt(resourceRow('r-alpha'), column)).getByRole('link');
    expect(link).toHaveTextContent(/unplaced/i);
    expect(link).toHaveAttribute('href', '/configuration');
    expect(link).toHaveAttribute('title');
  });

  it('explains "Ungraded" and links to where a criticality is declared', async () => {
    serve({ resources: [{ ...ALPHA, attributes: { zone: 'dmz' } }, BRAVO] });
    await resources();

    const column = columnIndex('Criticality');
    const link = within(cellAt(resourceRow('r-alpha'), column)).getByRole('link');
    expect(link).toHaveTextContent(/ungraded/i);
    expect(link).toHaveAttribute('href', '/configuration');
  });

  /**
   * When *nothing* is placed or graded, the column stops being a finding.
   *
   * Ninety-seven rows reading "Unplaced" and ninety-seven reading "Ungraded"
   * were two columns and roughly six hundred pixels carrying one word each, on
   * the screen that most needs to tell one row from another. That is a fact
   * about the deployment rather than about ninety-seven resources: it is said
   * once, above the table, with the same link the cells were carrying.
   */
  it('drops both columns when nothing in the estate is placed or graded', async () => {
    serve({
      resources: [
        { ...ALPHA, attributes: {} },
        { ...BRAVO, attributes: {} },
      ],
    });
    await resources();

    expect(screen.queryByRole('columnheader', { name: /zone/i })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /criticality/i })).toBeNull();

    const note = screen.getByTestId('estate-ungraded');
    expect(note).toHaveTextContent(/placed in a zone or graded/i);
    expect(within(note).getByRole('link')).toHaveAttribute('href', '/configuration');
  });

  it('drops only the column that carries nothing', async () => {
    serve({
      resources: [
        { ...ALPHA, attributes: { zone: 'dmz' } },
        { ...BRAVO, attributes: { zone: 'dmz' } },
      ],
    });
    await resources();

    expect(screen.getByRole('columnheader', { name: /zone/i })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: /criticality/i })).toBeNull();
    expect(screen.getByTestId('estate-ungraded')).toHaveTextContent(
      /graded for criticality/i,
    );
  });

  it('leaves a declared zone and criticality as plain values, with no link', async () => {
    serve({ resources: [ALPHA] });
    await resources();

    const zoneColumn = columnIndex('Zone');
    expect(
      within(cellAt(resourceRow('r-alpha'), zoneColumn)).queryByRole('link'),
    ).toBeNull();
    const criticalityColumn = columnIndex('Criticality');
    expect(
      within(cellAt(resourceRow('r-alpha'), criticalityColumn)).queryByRole('link'),
    ).toBeNull();
  });

  it('tells the reader the default sort has an alternative', async () => {
    serve({ resources: [ALPHA, BRAVO] });
    await resources();

    expect(screen.getByText(/worst first/i)).toHaveAttribute(
      'title',
      expect.stringMatching(/column heading/i),
    );
  });
});

describe('resources: a filter by name', () => {
  it('narrows the table to resources whose name matches, case-insensitively', async () => {
    serve({ resources: [ALPHA, BRAVO] });
    await resources({ q: 'BRA' });

    expect(screen.queryByTestId('row-list')).toHaveTextContent('bravo');
    expect(screen.getAllByTestId('row')).toHaveLength(1);
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
    expect(within(form).getByDisplayValue('critical')).toBeInTheDocument();
  });
});

describe('resources: a filter by health', () => {
  it('applies the healthy value carried by the dashboard drill-down', async () => {
    serve({ resources: [ALPHA, BRAVO, CHARLIE] });
    await resources({ health: 'healthy' });

    expect(screen.getAllByTestId('row')).toHaveLength(1);
    expect(screen.getByTestId('row')).toHaveAttribute('data-row', 'r-alpha');
  });

  it('groups degraded and unhealthy resources under the problem drill-down', async () => {
    serve({ resources: [ALPHA, BRAVO, CHARLIE] });
    await resources({ health: 'problem' });

    const rows = screen.getAllByTestId('row');
    expect(rows).toHaveLength(2);
    const ids = rows.map((row) => row.getAttribute('data-row'));
    expect(ids).toEqual(expect.arrayContaining(['r-bravo', 'r-charlie']));
    expect(ids).not.toContain('r-alpha');
    expect(screen.getByText('bravo')).toBeInTheDocument();
    expect(screen.getByText('charlie')).toBeInTheDocument();
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
    // A banner promising to resume a wizard with nothing left to resume
    // would be a control that lies, so it is absent rather than shown and
    // pointless.
    serveWithChecklist(true);
    await resources({ return: 'setup' });

    expect(screen.queryByTestId('setup-return-banner')).toBeNull();
  });
});
