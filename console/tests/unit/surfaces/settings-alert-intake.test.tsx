import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { AlertIntakeScreen } from '@/surfaces/settings/alert-intake';

import {
  principalHolding,
  serveScenario,
  serveScenarioExcept,
} from '../support/dataset';

/**
 * Alert intake: the receiver list inverted, action first.
 *
 * The tab this replaced showed every receiver's payload, headers and
 * signature expanded by default, with the copy button and the token buried
 * in the prose between them. This pins the opposite shape: a compact row an
 * operator can act on immediately, and the documentation one press away —
 * never open on load, which is also what keeps the page inside its scroll
 * budget.
 */

/** A base for parsing a path-only address. Never contacted, and built rather
 * than written — the same convention `support/dataset.ts` uses. */
const FIXTURE_BASE = ['http:', '//fixtures.invalid'].join('');

/**
 * The address a deployment's own network path produced for `pagerduty` in one
 * observed case: the scheme and host this test's fetch stub swaps in, never a
 * literal origin.
 */
const UNSAFE_PAGERDUTY_URL = ['http:', '//192.168.68.74:8420/webhooks/pagerduty'].join(
  '',
);

interface IngressSourcesBody {
  readonly sources: readonly { readonly source: string; readonly url: string }[];
}

/**
 * `serveScenario('populated')`, with one receiver's paste-ready address
 * swapped for the shape a real deployment produced: an http:// address
 * carrying an internal IP, echoed back by a request the console's own server
 * made to the gateway rather than one an outside alert router could reach.
 */
function serveWithUnsafeIngressUrl(): void {
  serveScenario('populated');
  const base = globalThis.fetch;
  vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), FIXTURE_BASE).pathname;
    const response = await base(input as string, init);
    if (path !== '/v1/ingress/sources') return response;
    const body = (await response.json()) as IngressSourcesBody;
    return new Response(
      JSON.stringify({
        ...body,
        sources: body.sources.map((row) =>
          row.source === 'pagerduty' ? { ...row, url: UNSAFE_PAGERDUTY_URL } : row,
        ),
      }),
      { status: response.status, headers: { 'content-type': 'application/json' } },
    );
  });
}

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

async function page(
  scenario: 'populated' | 'empty' = 'populated',
  principal?: unknown,
): Promise<void> {
  serveScenario(scenario, principal);
  render(await AlertIntakeScreen(await surfaceContext({})));
}

function sourceRow(name: string): HTMLElement | undefined {
  return screen
    .getAllByTestId('ingress-source')
    .find((row) => row.getAttribute('data-source') === name);
}

function requireSourceRow(name: string): HTMLElement {
  const row = sourceRow(name);
  if (row === undefined) throw new Error(`no ingress source row for ${name}`);
  return row;
}

/** Opens `row`'s collapsed detail — the one control the compact row keeps closed. */
async function expandDetail(row: HTMLElement): Promise<void> {
  await userEvent.click(within(row).getByRole('button', { name: /format & test/i }));
}

describe('the page itself', () => {
  it('carries the Settings header, addressed as settings-alert-intake', async () => {
    await page();

    expect(screen.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-alert-intake',
    );
    expect(screen.getByTestId('page-header')).toHaveTextContent('Alert intake');
  });
});

describe('the receiver list, compact by default', () => {
  it('shows a name, an activity chip and a copyable endpoint per receiver, with nothing expanded', async () => {
    await page();

    const rows = screen.getAllByTestId('ingress-source');
    expect(rows.length).toBe(7);
    // No reference content is in the document at all until it is asked for.
    expect(screen.queryByTestId('reference-body')).toBeNull();
    expect(screen.queryByTestId('rule-simulator')).toBeNull();
    expect(screen.queryByTestId('sample')).toBeNull();

    const live = requireSourceRow('alertmanager');
    expect(within(live).getByTestId('ingress-url')).toBeInTheDocument();
    expect(within(live).getByTestId('last-delivery')).toBeInTheDocument();
  });

  it('offers the detail one press away, closed rather than absent', async () => {
    await page();

    const row = requireSourceRow('alertmanager');
    const disclosure = within(row).getByTestId('reference');
    expect(disclosure).toHaveAttribute('data-expanded', 'false');

    await expandDetail(row);

    expect(within(row).getByTestId('reference')).toHaveAttribute(
      'data-expanded',
      'true',
    );
    expect(within(row).getByTestId('reference-body')).toBeInTheDocument();
  });
});

describe('a source that has never delivered', () => {
  it('says so, rather than showing an empty row', async () => {
    await page();

    const silent = sourceRow('sentry');
    expect(silent?.getAttribute('data-never-delivered')).toBe('true');
    expect(silent).toHaveTextContent('Nothing has ever arrived here');
  });

  it('is drawn before the ones that have', async () => {
    await page();

    const first = screen.getAllByTestId('ingress-source')[0];
    expect(first?.getAttribute('data-never-delivered')).toBe('true');
  });

  it('is every row on a deployment where nothing has arrived at all', async () => {
    await page('empty');

    const rows = screen.getAllByTestId('ingress-source');
    expect(rows.length).toBe(7);
    expect(
      rows.every((row) => row.getAttribute('data-never-delivered') === 'true'),
    ).toBe(true);
  });

  it('is neutral rather than styled as an error', async () => {
    await page('empty');

    for (const marker of screen.getAllByTestId('never-delivered')) {
      expect(marker.className).not.toContain('text-danger');
      expect(marker.className).toContain('text-muted');
    }
  });
});

describe('a source that has delivered, and one that was refused', () => {
  it('shows when it last delivered and carries the accepted outcome, unalarmingly', async () => {
    await page();

    const live = requireSourceRow('alertmanager');
    expect(live.getAttribute('data-never-delivered')).toBe('false');
    const chip = within(live).getByTestId('last-delivery');
    expect(chip).toHaveTextContent('Last delivery');
    expect(chip).toHaveTextContent('accepted');
    // Accepted is not a status this palette has any reason to alarm on.
    const badge = within(chip).getByText('accepted');
    expect(badge.closest('[data-role]')).not.toHaveAttribute('data-role', 'danger');
  });

  it('draws a recent rejection in the danger role — silence and refusal are not the same chip', async () => {
    await page();

    const refusing = requireSourceRow('grafana');
    const chip = within(refusing).getByTestId('last-delivery');
    expect(chip).toHaveTextContent('rejected');
    const badge = within(chip).getByText('rejected');
    expect(badge.closest('[data-role]')).toHaveAttribute('data-role', 'danger');

    // The row is not merely styled as danger — the reason is right there,
    // not one click away, which is what makes it actionable rather than
    // merely alarming.
    expect(within(refusing).getByTestId('rejections')).toHaveTextContent(
      'did not verify',
    );
  });

  it('shows the masked sample beside the policy that produced it, once expanded', async () => {
    await page();

    const live = requireSourceRow('alertmanager');
    await expandDetail(live);

    const sample = within(live).getByTestId('sample');
    expect(sample).toHaveTextContent('standard');
    expect(sample).toHaveTextContent('ContainerMemoryHigh');
  });
});

describe('the receiver detail, once expanded', () => {
  it('names the expected format and the trust mechanism', async () => {
    await page();

    const row = requireSourceRow('alertmanager');
    await expandDetail(row);

    const body = within(row).getByTestId('reference-body');
    expect(body).toHaveTextContent('groupKey');
    expect(body).toHaveTextContent('Authorization');
  });

  it('carries a delivery test scoped to this one receiver, for a viewer who may change routing', async () => {
    await page();

    const row = requireSourceRow('alertmanager');
    await expandDetail(row);

    const tester = within(row).getByTestId('delivery-tester');
    expect(
      within(tester).getByRole('heading', { name: 'Test a delivery' }),
    ).toBeInTheDocument();
    const simulator = within(tester).getByTestId('rule-simulator');
    // Scoped: the source select carries exactly this receiver, not a choice
    // of all seven — the question being asked is "what would a payload from
    // *this* receiver do", from the row it was opened on.
    const options = within(simulator).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual(['alertmanager']);
  });

  it('is entirely absent for a reader who cannot change routing', async () => {
    // Absent, not disabled: a control a person cannot use, sitting under a
    // heading naming a feature they cannot reach, teaches them the console
    // is broken rather than that they lack a permission.
    await page('populated', principalHolding(['config.read']));

    const row = requireSourceRow('alertmanager');
    await expandDetail(row);

    expect(within(row).queryByTestId('delivery-tester')).toBeNull();
    expect(within(row).queryByTestId('rule-simulator')).toBeNull();
  });
});

describe('the routing rules', () => {
  it('are numbered in the order they are evaluated', async () => {
    await page();

    const rules = screen.getByTestId('routing-rules');
    expect(rules).toHaveTextContent('1. critical-to-platform');
    expect(rules).toHaveTextContent('2. everything-else');
  });

  it('always draw the one that decides everything nothing else matched', async () => {
    await page();

    const catchAll = screen.getByTestId('catch-all-rule');
    expect(catchAll).toHaveTextContent('everything-else');
    expect(screen.getByTestId('catch-all-note')).toHaveTextContent(
      'Everything no rule above matched ends here.',
    );
  });

  it('draw the catch-all even on a deployment that has configured nothing', async () => {
    await page('empty');

    expect(screen.getByTestId('catch-all-rule')).toHaveTextContent('catch-all');
  });

  it('carries no embedded simulator of its own — that moved to each receiver', async () => {
    await page();

    const rules = screen.getByTestId('routing-rules').closest('[data-testid="panel"]');
    expect(rules).not.toBeNull();
    expect(within(rules as HTMLElement).queryByTestId('rule-simulator')).toBeNull();
  });
});

describe('a webhook address safe to announce', () => {
  it('is copyable in one click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    await page();
    const row = requireSourceRow('alertmanager');
    await userEvent.click(within(row).getByTestId('ingress-url-copy'));

    expect(writeText).toHaveBeenCalledWith(
      ['https:', '//ninjasre.example.invalid/webhooks/alertmanager'].join(''),
    );
    vi.unstubAllGlobals();
  });
});

describe('a webhook address that is not safe to announce', () => {
  it('never prints an http:// address on this page', async () => {
    serveWithUnsafeIngressUrl();
    render(await AlertIntakeScreen(await surfaceContext({})));

    const row = sourceRow('pagerduty');
    expect(row?.textContent).not.toContain(['http', '://'].join(''));
  });

  it('falls back to the path, which is still copyable in one click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    serveWithUnsafeIngressUrl();
    render(await AlertIntakeScreen(await surfaceContext({})));
    const row = requireSourceRow('pagerduty');
    await userEvent.click(within(row).getByTestId('ingress-url-copy'));

    expect(writeText).toHaveBeenCalledWith('/webhooks/pagerduty');
    vi.unstubAllGlobals();
  });
});

describe('the delivery token control', () => {
  it('sits beside what it is scoped to, rather than orphaned below the rows', async () => {
    await page();

    const group = screen.getByTestId('delivery-token-group');
    expect(group).toHaveTextContent('webhook.deliver');
    expect(within(group).getByTestId('delivery-token')).toBeInTheDocument();
  });
});

describe('provenance', () => {
  it('answers which rule caught an arrival, which team it went to, and which run', async () => {
    await page();

    const live = requireSourceRow('alertmanager');
    const chain = live.querySelector('[data-testid="provenance-chain"]');
    expect(chain).toHaveTextContent('critical-to-platform');
    expect(chain).toHaveTextContent('team-platform');
    expect(chain).toHaveTextContent('proxmox:container/hal9000/110');
  });

  it('links the run, which is where the finding names its query and instant', async () => {
    await page();

    const live = requireSourceRow('alertmanager');
    const link = live.querySelector('[data-testid="provenance-run"]');
    expect(link).toBeDefined();
    expect(link?.getAttribute('href')).toMatch(/^\/runs\//);
  });

  it('says plainly when there is nothing to trace', async () => {
    await page('empty');

    expect(screen.getAllByTestId('provenance-none').length).toBe(7);
  });

  it('names how many deliveries the disclosure holds, before it is opened', async () => {
    await page();

    const live = requireSourceRow('alertmanager').querySelector(
      '[data-testid="provenance"] summary',
    );
    expect(live).toHaveTextContent('Where did this go? (1)');

    const silent = requireSourceRow('datadog').querySelector(
      '[data-testid="provenance"] summary',
    );
    expect(silent).toHaveTextContent('Where did this go? (0)');
  });
});

describe('a column whose read the deployment refused', () => {
  it('fails alone, leaving the receiver list standing', async () => {
    serveScenarioExcept('populated', ['/v1/transit/rules']);
    render(await AlertIntakeScreen(await surfaceContext({})));

    const failed = screen
      .getAllByTestId('panel')
      .filter((panel) => panel.getAttribute('data-state') === 'error');
    expect(failed.length).toBe(1);
    expect(screen.getAllByTestId('ingress-source').length).toBe(7);
  });
});

describe('the setup wizard handover', () => {
  it('offers the way back only when the address asks and setup is unfinished', async () => {
    await page();

    expect(screen.queryByTestId('setup-return-banner')).toBeNull();
  });
});
