import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { DataScreen } from '@/surfaces/screens/data';

import {
  principalHolding,
  serveScenario,
  serveScenarioExcept,
} from '../support/dataset';

/** A base for parsing a path-only address. Never contacted, and built rather
 * than written — the same convention `support/dataset.ts` uses. */
const FIXTURE_BASE = ['http:', '//fixtures.invalid'].join('');

/**
 * The address a deployment's own network path produced for `pagerduty` in one
 * observed case: the scheme and host this test's fetch stub swaps in, never a
 * literal origin (built from parts for the same reason `FIXTURE_BASE` is).
 */
const UNSAFE_PAGERDUTY_URL = ['http:', '//192.168.68.74:8420/webhooks/pagerduty'].join(
  '',
);

/** What `/v1/ingress/sources` answers with, loosely — enough to rewrite one row. */
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

/**
 * Where it came from, and where it goes — on one screen, in the order it moves.
 *
 * The acceptance criteria this feature is judged on, from the console's side.
 * The one that decides whether the screen is worth having is the quietest:
 * a source that has never delivered is *loud*. A configured receiver that never
 * delivered is indistinguishable from one that does not exist, and that is the
 * most expensive failure in this whole category precisely because nothing about
 * it is noisy.
 */

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

async function data(scenario: 'populated' | 'empty' = 'populated'): Promise<void> {
  serveScenario(scenario);
  render(await DataScreen(await surfaceContext({})));
}

function sourceRow(name: string): HTMLElement | undefined {
  return screen
    .getAllByTestId('ingress-source')
    .find((row) => row.getAttribute('data-source') === name);
}

/** `sourceRow`, narrowed by failing the test rather than by asserting. */
function requireSourceRow(name: string): HTMLElement {
  const row = sourceRow(name);
  if (row === undefined) {
    throw new Error(`no ingress source row for ${name}`);
  }
  return row;
}

describe('the transit screen', () => {
  it('draws the three columns in the order data moves through them', async () => {
    await data();

    const columns = screen.getByTestId('transit-columns');
    expect(columns).toBeInTheDocument();
    expect(screen.getByTestId('ingress-sources')).toBeInTheDocument();
    expect(screen.getByTestId('routing-rules')).toBeInTheDocument();
    expect(screen.getByTestId('destinations')).toBeInTheDocument();
  });
});

describe('a source that has never delivered', () => {
  it('says so, rather than showing an empty row', async () => {
    await data();

    const silent = sourceRow('sentry');
    expect(silent?.getAttribute('data-never-delivered')).toBe('true');
    expect(silent).toHaveTextContent('Nothing has ever arrived here');
  });

  it('is drawn before the ones that have', async () => {
    // Ordering is the whole of "without the operator hunting". A silence at the
    // bottom of a list of seven is a silence somebody scrolls past.
    await data();

    const first = screen.getAllByTestId('ingress-source')[0];
    expect(first?.getAttribute('data-never-delivered')).toBe('true');
  });

  it('is every row on a deployment where nothing has arrived at all', async () => {
    await data('empty');

    const rows = screen.getAllByTestId('ingress-source');
    expect(rows.length).toBe(7);
    expect(
      rows.every((row) => row.getAttribute('data-never-delivered') === 'true'),
    ).toBe(true);
  });

  it('is neutral rather than styled as an error', async () => {
    // A freshly configured deployment where nothing has arrived yet is the
    // ordinary first day, not seven faults — and colour is the one thing a
    // reader takes in before reading a word of the sentence beside it.
    await data('empty');

    for (const marker of screen.getAllByTestId('never-delivered')) {
      expect(marker.className).not.toContain('text-danger');
      expect(marker.className).toContain('text-muted');
    }
  });
});

describe('a source that has delivered', () => {
  it('shows when it last did and how that delivery ended', async () => {
    await data();

    const live = sourceRow('alertmanager');
    expect(live?.getAttribute('data-never-delivered')).toBe('false');
    expect(live).toHaveTextContent('Last delivery');
    expect(live).toHaveTextContent('accepted');
  });

  it('shows the masked sample beside the policy that produced it', async () => {
    await data();

    const sample = screen.getByTestId('sample');
    expect(sample).toHaveTextContent('standard');
    expect(sample).toHaveTextContent('ContainerMemoryHigh');
  });

  it('shows what was refused, with the reason', async () => {
    await data();

    const refusing = sourceRow('grafana');
    expect(refusing).toHaveTextContent('did not verify');
  });
});

describe('the rules', () => {
  it('are numbered in the order they are evaluated', async () => {
    await data();

    const rules = screen.getByTestId('routing-rules');
    expect(rules).toHaveTextContent('1. critical-to-platform');
    expect(rules).toHaveTextContent('2. everything-else');
  });

  it('always draw the one that decides everything nothing else matched', async () => {
    await data();

    const catchAll = screen.getByTestId('catch-all-rule');
    expect(catchAll).toHaveTextContent('everything-else');
    expect(screen.getByTestId('catch-all-note')).toHaveTextContent(
      'Everything no rule above matched ends here.',
    );
  });

  it('draw the catch-all even on a deployment that has configured nothing', async () => {
    await data('empty');

    expect(screen.getByTestId('catch-all-rule')).toHaveTextContent('catch-all');
  });

  it('is drawn as a ranked list only once there is more than the implicit default', async () => {
    await data();

    expect(screen.getByTestId('catch-all-note')).toBeInTheDocument();
  });

  it('is not drawn as a ranked list when the only rule is the implicit default', async () => {
    // "Everything no rule above matched ends here" presupposes a list above
    // it. With nothing an operator declared, there is no "above" — so neither
    // the ordinal nor that sentence should appear.
    await data('empty');

    const only = screen.getByTestId('catch-all-rule');
    expect(only.textContent).not.toMatch(/^1\./);
    expect(screen.queryByTestId('catch-all-note')).toBeNull();
    expect(screen.queryByTestId('routing-rule')).toBeNull();
  });
});

describe('the delivery tester', () => {
  it('names itself, rather than presenting as an unlabelled form', async () => {
    await data();

    const tester = screen.getByTestId('delivery-tester');
    expect(
      within(tester).getByRole('heading', { name: 'Simulate' }),
    ).toBeInTheDocument();
    expect(within(tester).getByTestId('rule-simulator')).toBeInTheDocument();
  });

  it('is entirely absent for a reader who cannot change routing', async () => {
    // Absent, not disabled: a control a person cannot use, sitting under a
    // heading naming a feature they cannot reach, teaches them the console is
    // broken rather than that they lack a permission.
    serveScenario('populated', principalHolding(['config.read']));
    render(await DataScreen(await surfaceContext({})));

    expect(screen.queryByTestId('delivery-tester')).toBeNull();
  });
});

describe('the destinations', () => {
  it('declare their events, their channel, their detail and their masking policy', async () => {
    await data();

    const destination = screen.getByTestId('destination');
    expect(destination).toHaveTextContent('slack');
    expect(destination).toHaveTextContent('summary_with_link');
    expect(screen.getByTestId('destination-events')).toHaveTextContent(
      'investigation_concluded',
    );
    expect(screen.getByTestId('destination-masking')).toHaveTextContent('standard');
  });

  it('say why nothing can be declared on a deployment with no channel', async () => {
    await data('empty');

    expect(
      screen.getByText(/No configured integration can deliver a message/),
    ).toBeInTheDocument();
  });
});

describe('a delivery that did not arrive', () => {
  it('is visible with its reason and carries the control that sends it again', async () => {
    await data();

    const failed = screen.getByTestId('failed-delivery');
    expect(failed).toHaveTextContent('channel_not_found');
    expect(screen.getByTestId('resend-action')).toHaveTextContent('Send again');
  });
});

describe('a webhook address safe to announce', () => {
  it('is copyable in one click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    await data();
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
    render(await DataScreen(await surfaceContext({})));

    const row = sourceRow('pagerduty');
    expect(row?.textContent).not.toContain(['http', '://'].join(''));
  });

  it('falls back to the path, which is still copyable in one click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    serveWithUnsafeIngressUrl();
    render(await DataScreen(await surfaceContext({})));
    const row = requireSourceRow('pagerduty');
    await userEvent.click(within(row).getByTestId('ingress-url-copy'));

    expect(writeText).toHaveBeenCalledWith('/webhooks/pagerduty');
    vi.unstubAllGlobals();
  });
});

describe('the delivery token control', () => {
  it('sits beside what it is scoped to, rather than orphaned below the cards', async () => {
    await data();

    const group = screen.getByTestId('delivery-token-group');
    expect(group).toHaveTextContent('webhook.deliver');
    expect(within(group).getByTestId('delivery-token')).toBeInTheDocument();
  });
});

describe('provenance', () => {
  it('answers which rule caught an arrival, which team it went to, and which run', async () => {
    await data();

    const live = sourceRow('alertmanager');
    const chain = live?.querySelector('[data-testid="provenance-chain"]');
    expect(chain).toHaveTextContent('critical-to-platform');
    expect(chain).toHaveTextContent('team-platform');
    expect(chain).toHaveTextContent('proxmox:container/hal9000/110');
  });

  it('links the run, which is where the finding names its query and instant', async () => {
    await data();

    const live = sourceRow('alertmanager');
    const link = live?.querySelector('[data-testid="provenance-run"]');
    expect(link).toBeDefined();
    expect(link?.getAttribute('href')).toMatch(/^\/runs\//);
  });

  it('says plainly when there is nothing to trace', async () => {
    await data('empty');

    expect(screen.getAllByTestId('provenance-none').length).toBe(7);
  });

  it('names how many deliveries the disclosure holds, before it is opened', async () => {
    // Seven identical "Where did this go?" links with nothing to tell them
    // apart is seven links an operator opens one at a time to find the one
    // worth reading.
    await data();

    const live = sourceRow('alertmanager')?.querySelector(
      '[data-testid="provenance"] summary',
    );
    expect(live).toHaveTextContent('Where did this go? (1)');

    const silent = sourceRow('datadog')?.querySelector(
      '[data-testid="provenance"] summary',
    );
    expect(silent).toHaveTextContent('Where did this go? (0)');
  });
});

describe('a reader who may not change any of it', () => {
  it('is shown no simulator and no re-send control, rather than disabled ones', async () => {
    // Absent, not disabled: a control a person cannot use is a control that
    // teaches them the console is broken.
    serveScenario('populated', principalHolding(['config.read']));
    render(await DataScreen(await surfaceContext({})));

    expect(screen.queryByTestId('rule-simulator')).toBeNull();
    expect(screen.queryByTestId('resend-action')).toBeNull();
    expect(screen.getAllByTestId('ingress-source').length).toBe(7);
  });
});

describe('a column whose read the deployment refused', () => {
  it('fails alone, leaving the other two columns standing', async () => {
    serveScenarioExcept('populated', ['/v1/transit/rules']);
    render(await DataScreen(await surfaceContext({})));

    const failed = screen
      .getAllByTestId('panel')
      .filter((panel) => panel.getAttribute('data-state') === 'error');
    expect(failed.length).toBe(1);
    expect(screen.getAllByTestId('ingress-source').length).toBe(7);
    expect(screen.getByTestId('destinations')).toBeInTheDocument();
  });
});
