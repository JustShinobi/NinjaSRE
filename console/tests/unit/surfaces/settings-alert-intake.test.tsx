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
 * The address a deployment's own network path produced for `grafana` in one
 * observed case: the scheme and host this test's fetch stub swaps in, never a
 * literal origin.
 */
const UNSAFE_GRAFANA_URL = ['http:', '//192.168.68.74:8420/webhooks/grafana'].join('');

interface IngressSourcesBody {
  readonly sources: readonly { readonly source: string; readonly url: string }[];
}

interface IdentityTokensBody {
  readonly tokens: readonly Record<string, unknown>[];
}

/** The permission a token must carry to authenticate an inbound delivery. */
const DELIVERY_SCOPE = ['webhook', 'deliver'].join('.');

/** One delivery-scoped token, as `/identity/tokens` serves it. */
function deliveryToken(fields: {
  readonly name: string;
  readonly createdAt: string;
  readonly revoked?: boolean;
}): Record<string, unknown> {
  return {
    token_id: `tok-${fields.name}`,
    user_id: 'user-automation',
    name: fields.name,
    description: '',
    team_node_id: null,
    scopes: [DELIVERY_SCOPE],
    created_at: fields.createdAt,
    expires_at: null,
    last_used_at: null,
    revoked: fields.revoked ?? false,
  };
}

/**
 * `serveScenario('populated')`, with `/identity/tokens` answering exactly the
 * delivery-scoped tokens named here and no others.
 *
 * The dataset's own delivery token is filtered out first, which is the whole
 * point: a test that only appended would be asserting against whatever the
 * shared fixture happened to hold that week, and four tests in this block did
 * exactly that until the dataset grew a delivery token of its own and they all
 * went red at once. Passing no token is how "nobody has issued one" is stated
 * here, rather than borrowed from a scenario that never promised it.
 */
function serveWithDeliveryTokens(...tokens: readonly Record<string, unknown>[]): void {
  serveScenario('populated');
  const base = globalThis.fetch;
  vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), FIXTURE_BASE).pathname;
    const response = await base(input as string, init);
    if (path !== '/identity/tokens') return response;
    const body = (await response.json()) as IdentityTokensBody;
    const scopesOf = (token: Record<string, unknown>): readonly string[] =>
      Array.isArray(token.scopes) ? (token.scopes as readonly string[]) : [];
    return new Response(
      JSON.stringify({
        ...body,
        tokens: [
          ...body.tokens.filter((token) => !scopesOf(token).includes(DELIVERY_SCOPE)),
          ...tokens,
        ],
      }),
      { status: response.status, headers: { 'content-type': 'application/json' } },
    );
  });
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
          row.source === 'grafana' ? { ...row, url: UNSAFE_GRAFANA_URL } : row,
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
    expect(rows.length).toBe(3);
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
    // FR-050: the exact chip a silent source carries. Replaces the sentence
    // this test pinned before the chip vocabulary existed
    // ("Nothing has ever arrived here") — the words changed, the property
    // this test protects (a silent source says so, plainly) did not.
    await page();

    const silent = sourceRow('generic');
    expect(silent?.getAttribute('data-never-delivered')).toBe('true');
    expect(silent).toHaveTextContent('Ready — nothing arrived yet');
  });

  it('is drawn before the ones that have', async () => {
    await page();

    const first = screen.getAllByTestId('ingress-source')[0];
    expect(first?.getAttribute('data-never-delivered')).toBe('true');
  });

  it('is every row on a deployment where nothing has arrived at all', async () => {
    await page('empty');

    const rows = screen.getAllByTestId('ingress-source');
    expect(rows.length).toBe(3);
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

describe('the Receiving chip, the week volume, and the compact silent row', () => {
  it('carries the exact "Receiving" chip, distinct from the silent "Ready" one', async () => {
    await page();

    const live = requireSourceRow('alertmanager');
    expect(within(live).getByText('Receiving', { exact: true })).toBeInTheDocument();

    const silent = requireSourceRow('generic');
    expect(
      within(silent).getByText('Ready — nothing arrived yet', { exact: true }),
    ).toBeInTheDocument();
    expect(within(silent).queryByText('Receiving', { exact: true })).toBeNull();
  });

  it('states the week volume beside the last delivery, for the receiving source', async () => {
    await page();

    const live = requireSourceRow('alertmanager');
    expect(within(live).getByTestId('last-delivery')).toHaveTextContent('14 this week');
  });

  it('keeps the endpoint and the disclosure closed for a silent source, reachable one press away', async () => {
    await page();

    const silent = requireSourceRow('generic');
    // Nothing the compact row defers is in the document at all until it is
    // opened — the same "closed rather than absent" contract the receiving
    // row's own `Reference` already keeps.
    expect(within(silent).queryByTestId('ingress-url')).toBeNull();
    expect(within(silent).queryByTestId('reference-body')).toBeNull();

    const disclosure = within(silent).getByTestId('reference');
    expect(disclosure).toHaveAttribute('data-expanded', 'false');

    await expandDetail(silent);

    expect(within(silent).getByTestId('ingress-url')).toBeInTheDocument();
  });

  it('never shows the week volume or a last-delivery time on the silent row', async () => {
    await page();

    const silent = requireSourceRow('generic');
    expect(silent).not.toHaveTextContent('this week');
    expect(silent.querySelector('[data-testid="last-delivery"]')).toBeNull();
  });
});

describe('a silent source with a recent rejection', () => {
  /**
   * `serveScenario('populated')`, with `generic`'s ingress row swapped for one
   * that is `never_delivered` yet still carries a `recent_rejections` entry —
   * the shape FR-065's edge case names: something arrived and was refused
   * outside the window that decides "receiving" versus "silent", and the
   * refusal must not disappear into "nothing arrived".
   */
  function serveSilentSourceWithARejection(): void {
    serveScenario('populated');
    const base = globalThis.fetch;
    vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
      const path = new URL(String(input), FIXTURE_BASE).pathname;
      const response = await base(input as string, init);
      if (path !== '/v1/transit/ingress') return response;
      const body = (await response.json()) as {
        readonly sources: readonly Record<string, unknown>[];
      };
      return new Response(
        JSON.stringify({
          ...body,
          sources: body.sources.map((row) =>
            row.source === 'generic'
              ? {
                  ...row,
                  recent_rejections: [
                    {
                      delivery_id: 'generic:rejected',
                      direction: 'ingress',
                      source: 'generic',
                      occurred_at: '2026-08-01T00:00:00+00:00',
                      outcome: 'rejected',
                      reason: 'this generic webhook did not verify',
                      matched_rule: '',
                      team_node_id: '',
                      resource_id: '',
                      run_id: '',
                      incident_id: '',
                      event_type: '',
                      attempt: 1,
                      detail: {},
                    },
                  ],
                }
              : row,
          ),
        }),
        { status: response.status, headers: { 'content-type': 'application/json' } },
      );
    });
  }

  it('still shows the rejection, without the row reading as though nothing arrived', async () => {
    serveSilentSourceWithARejection();
    render(await AlertIntakeScreen(await surfaceContext({})));

    const silent = requireSourceRow('generic');
    expect(silent.getAttribute('data-never-delivered')).toBe('true');
    expect(
      within(silent).getByText('Ready — nothing arrived yet', { exact: true }),
    ).toBeInTheDocument();
    expect(within(silent).getByTestId('rejections')).toHaveTextContent(
      'this generic webhook did not verify',
    );
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

  it('names the action "Copy URL", not the raw-payload label it borrowed', async () => {
    // FR-052, read literally: the button this row offers is named "Copy
    // URL" — not "Copy the raw payload", the label of an unrelated control
    // (`surface.payload.copy`) this row was reading by mistake.
    await page();

    const row = requireSourceRow('alertmanager');
    expect(within(row).getByTestId('ingress-url-copy')).toHaveTextContent('Copy URL');
  });
});

describe('the Alertmanager receiver YAML', () => {
  it('offers "Copy Alertmanager receiver YAML" only on the Alertmanager row', async () => {
    await page();

    const live = requireSourceRow('alertmanager');
    expect(
      within(live).getByRole('button', { name: 'Copy Alertmanager receiver YAML' }),
    ).toBeInTheDocument();

    for (const name of ['grafana', 'generic']) {
      const row = requireSourceRow(name);
      expect(
        within(row).queryByRole('button', { name: 'Copy Alertmanager receiver YAML' }),
      ).toBeNull();
    }
  });

  it('copies exactly the block the gateway served, never a value assembled on the screen', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    await page();
    const live = requireSourceRow('alertmanager');
    await userEvent.click(
      within(live).getByRole('button', { name: 'Copy Alertmanager receiver YAML' }),
    );

    expect(writeText).toHaveBeenCalledTimes(1);
    const copied = writeText.mock.calls[0]?.[0] as string;
    expect(copied).toContain('webhook_configs');
    expect(copied).toContain(
      ['https:', '//ninjasre.example.invalid/webhooks/alertmanager'].join(''),
    );
    expect(copied).toContain('Alert delivery');
    // Never a value assembled by string concatenation on the screen: the
    // gateway's own marker sentence, verbatim, never a raw secret shape.
    expect(copied).toContain('paste the value of delivery token');
    vi.unstubAllGlobals();
  });

  it('offers no receiver-YAML action when the gateway generated none', async () => {
    // Mirrors FR-063's own rule for the trust line, applied to the YAML
    // action: no delivery token, no block that could not authenticate
    // anything — the gateway's own answer for that case is a `null`
    // `receiver_yaml`, never a block the screen would have to assemble
    // itself to fill the gap.
    serveScenario('populated');
    const base = globalThis.fetch;
    vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
      const path = new URL(String(input), FIXTURE_BASE).pathname;
      const response = await base(input as string, init);
      if (path !== '/v1/ingress/sources') return response;
      const body = (await response.json()) as {
        readonly sources: readonly Record<string, unknown>[];
      };
      return new Response(
        JSON.stringify({
          ...body,
          sources: body.sources.map((row) =>
            row.source === 'alertmanager' ? { ...row, receiver_yaml: null } : row,
          ),
        }),
        { status: response.status, headers: { 'content-type': 'application/json' } },
      );
    });
    render(await AlertIntakeScreen(await surfaceContext({})));

    const live = requireSourceRow('alertmanager');
    expect(
      within(live).queryByRole('button', { name: 'Copy Alertmanager receiver YAML' }),
    ).toBeNull();
    vi.unstubAllGlobals();
  });
});

describe('security: no stored secret ever reaches the copied receiver block', () => {
  it('never carries a secret into the clipboard, even one sitting in a field this screen has no reason to read', async () => {
    // `receiver_yaml()` (gateway/webhooks/sources/alertmanager.py) has no
    // parameter a secret could travel through in the first place —
    // tests/contract/console/test_ingress_receiver_yaml_contract.py pins
    // that generator's own signature closed. This plants one on the wire
    // anyway, on a field this screen never reads into `receiverYaml`, so the
    // assertion below is about what this component does with what it is
    // given — the same idiom `integration-panel.test.tsx` already uses for
    // a credential value — not about what a well-behaved gateway would ever
    // actually send.
    const secret = 'ninja_wh_9f2b7c1e0d3a';
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    serveScenario('populated');
    const base = globalThis.fetch;
    vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
      const path = new URL(String(input), FIXTURE_BASE).pathname;
      const response = await base(input as string, init);
      if (path !== '/v1/ingress/sources') return response;
      const body = (await response.json()) as {
        readonly sources: readonly Record<string, unknown>[];
      };
      return new Response(
        JSON.stringify({
          ...body,
          sources: body.sources.map((row) =>
            row.source === 'alertmanager' ? { ...row, credential_value: secret } : row,
          ),
        }),
        { status: response.status, headers: { 'content-type': 'application/json' } },
      );
    });
    render(await AlertIntakeScreen(await surfaceContext({})));

    const live = requireSourceRow('alertmanager');
    await userEvent.click(
      within(live).getByRole('button', { name: 'Copy Alertmanager receiver YAML' }),
    );

    expect(writeText).toHaveBeenCalledTimes(1);
    const copied = writeText.mock.calls[0]?.[0] as string;
    expect(copied).not.toContain(secret);
    // FR-058: outside the issuance gesture, this marker stands in for the
    // value instead — still exactly what the gateway generated, unchanged
    // by the plant above.
    expect(copied).toContain('paste the value of delivery token');

    for (const element of document.body.querySelectorAll('*')) {
      expect(element.outerHTML).not.toContain(secret);
    }
    vi.unstubAllGlobals();
  });
});

describe('a webhook address that is not safe to announce', () => {
  it('never prints an http:// address on this page', async () => {
    serveWithUnsafeIngressUrl();
    render(await AlertIntakeScreen(await surfaceContext({})));

    const row = sourceRow('grafana');
    expect(row?.textContent).not.toContain(['http', '://'].join(''));
  });

  it('falls back to the path, which is still copyable in one click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    serveWithUnsafeIngressUrl();
    render(await AlertIntakeScreen(await surfaceContext({})));
    const row = requireSourceRow('grafana');
    await userEvent.click(within(row).getByTestId('ingress-url-copy'));

    expect(writeText).toHaveBeenCalledWith('/webhooks/grafana');
    vi.unstubAllGlobals();
  });
});

describe('the delivery token control', () => {
  it('sits beside what it is scoped to, rather than orphaned below the rows', async () => {
    // The default fixture already has a delivery token issued, so the
    // control this row offers is the navigation to rotate it, not the
    // inline mint — see the next few tests for both shapes named directly.
    await page();

    const group = screen.getByTestId('delivery-token-group');
    expect(within(group).getByTestId('delivery-token-rotate')).toBeInTheDocument();
  });

  it('never names the raw delivery permission, before or after a token authenticates it', async () => {
    await page();

    expect(screen.getByTestId('delivery-token-group')).not.toHaveTextContent(
      'webhook.deliver',
    );
  });

  it('says nothing has authenticated deliveries yet, when no token carries the permission', async () => {
    // Stated here rather than inherited: the deployment this renders has no
    // delivery-scoped token at all, which is the ordinary state of one that
    // has not issued one yet.
    serveWithDeliveryTokens();
    render(await AlertIntakeScreen(await surfaceContext({})));

    const group = screen.getByTestId('delivery-token-group');
    expect(group).toHaveTextContent(/no delivery token/i);
    expect(within(group).getByTestId('delivery-token')).toHaveTextContent(
      'Issue a delivery token',
    );
  });

  it('names the delivery token once one has actually authenticated deliveries with it', async () => {
    serveWithDeliveryTokens(
      deliveryToken({ name: 'am-cluster', createdAt: '2026-08-01T00:00:00+00:00' }),
    );
    render(await AlertIntakeScreen(await surfaceContext({})));

    const group = screen.getByTestId('delivery-token-group');
    expect(group).toHaveTextContent('am-cluster');
    expect(group).not.toHaveTextContent(DELIVERY_SCOPE);
  });

  it('offers to rotate, not to issue a second one, once a delivery token already exists', async () => {
    // FR-062: the offer is a navigation to Machine tokens, already narrowed
    // to the delivery scope — not a second mint behind this row. The inline
    // issue control (`delivery-token`) is exactly what "not to issue a
    // second one" rules out, so its absence is asserted directly.
    serveWithDeliveryTokens(
      deliveryToken({ name: 'am-cluster', createdAt: '2026-08-01T00:00:00+00:00' }),
    );
    render(await AlertIntakeScreen(await surfaceContext({})));

    const group = screen.getByTestId('delivery-token-group');
    expect(within(group).queryByTestId('delivery-token')).toBeNull();
    const rotate = within(group).getByTestId('delivery-token-rotate');
    expect(rotate).toHaveTextContent('Rotate');
    expect(rotate).not.toHaveTextContent('Issue a delivery token');
    expect(rotate.tagName).toBe('A');
    expect(rotate.getAttribute('href')).toBe(
      `/settings/machine-tokens?scope=${DELIVERY_SCOPE}`,
    );
  });

  it('picks the most recently issued token when more than one carries the permission', async () => {
    serveWithDeliveryTokens(
      deliveryToken({ name: 'am-cluster-old', createdAt: '2026-01-01T00:00:00+00:00' }),
      deliveryToken({ name: 'am-cluster-new', createdAt: '2026-08-01T00:00:00+00:00' }),
    );
    render(await AlertIntakeScreen(await surfaceContext({})));

    const group = screen.getByTestId('delivery-token-group');
    expect(group).toHaveTextContent('am-cluster-new');
    expect(group).not.toHaveTextContent('am-cluster-old');
  });

  it('never counts a revoked token as the one authenticating deliveries', async () => {
    serveWithDeliveryTokens(
      deliveryToken({
        name: 'am-cluster-revoked',
        createdAt: '2026-08-01T00:00:00+00:00',
        revoked: true,
      }),
    );
    render(await AlertIntakeScreen(await surfaceContext({})));

    const group = screen.getByTestId('delivery-token-group');
    expect(group).not.toHaveTextContent('am-cluster-revoked');
    expect(within(group).getByTestId('delivery-token')).toHaveTextContent(
      'Issue a delivery token',
    );
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

    expect(screen.getAllByTestId('provenance-none').length).toBe(3);
  });

  it('names how many deliveries the disclosure holds, before it is opened', async () => {
    await page();

    const live = requireSourceRow('alertmanager').querySelector(
      '[data-testid="provenance"] summary',
    );
    expect(live).toHaveTextContent('Where did this go? (1)');

    const silent = requireSourceRow('generic').querySelector(
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
    expect(screen.getAllByTestId('ingress-source').length).toBe(3);
  });
});

describe('the setup wizard handover', () => {
  it('offers the way back only when the address asks and setup is unfinished', async () => {
    await page();

    expect(screen.queryByTestId('setup-return-banner')).toBeNull();
  });
});

describe('the retired intake sources', () => {
  it('names what moved to the roadmap, and why', async () => {
    await page();

    const footer = screen.getByTestId('ingress-retired');
    expect(footer).toHaveTextContent('Sentry');
    expect(footer).toHaveTextContent('PagerDuty');
    expect(footer).toHaveTextContent('Opsgenie');
    expect(footer).toHaveTextContent('Datadog');
    expect(footer).toHaveTextContent('roadmap');
  });
});

const CONFIG_NODE = 'org-northwind';

interface ObservationConfigStub {
  readonly values?: unknown;
  readonly provenance?: Readonly<Record<string, string>>;
  readonly fields?: readonly unknown[];
}

/**
 * `serveScenario('populated')`, with the configuration-service reads the
 * advanced observation section makes answered directly — the shared dataset
 * carries no `policies.observation.*` values or fields yet.
 */
function serveWithObservationConfig(
  config: ObservationConfigStub = {},
  principal?: unknown,
): void {
  serveScenario('populated', principal);
  const base = globalThis.fetch;
  vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), FIXTURE_BASE).pathname;
    if (path === `/v1/config/${CONFIG_NODE}` && config.values !== undefined) {
      return new Response(
        JSON.stringify({
          node_id: CONFIG_NODE,
          values: config.values,
          provenance: config.provenance ?? {},
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      );
    }
    if (path === `/v1/config/${CONFIG_NODE}/fields` && config.fields !== undefined) {
      return new Response(JSON.stringify({ fields: config.fields }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }
    return base(input as string, init);
  });
}

describe('the advanced observation-settings section', () => {
  it('is collapsed on arrival and names the observation fields with no other control', async () => {
    serveWithObservationConfig({
      values: {
        policies: {
          observation: {
            paused: true,
            pause_reason: 'planned migration',
            bridge: { enabled: false },
            guardian: { enabled: false },
          },
        },
      },
      provenance: { 'policies.observation.paused': CONFIG_NODE },
    });

    render(await AlertIntakeScreen(await surfaceContext({})));

    const details = screen.getByTestId('advanced-config-policies-observation');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    const rows = screen.getAllByTestId('effective-field');
    const paths = rows.map((row) => row.getAttribute('data-path'));
    expect(paths).toContain('policies.observation.paused');
    expect(paths).toContain('policies.observation.pause_reason');
    expect(paths).toContain('policies.observation.bridge.enabled');
    expect(paths).toContain('policies.observation.guardian.enabled');
  });

  it('scopes its editor to policies.observation fields only, never a different section', async () => {
    serveWithObservationConfig({
      values: { policies: { observation: { paused: false } } },
      fields: [
        {
          path: 'policies.observation.paused',
          label: 'Watching paused',
          type: 'boolean',
          section: 'Observation',
          value: false,
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.sso.provider',
          label: 'Provider',
          type: 'string',
          section: 'Single sign-on',
          value: 'keycloak',
          provenance: CONFIG_NODE,
          set_here: true,
        },
      ],
    });

    render(await AlertIntakeScreen(await surfaceContext({})));

    const section = screen.getByTestId('advanced-config-policies-observation');
    const fields = section.querySelectorAll('[data-testid="config-field"]');
    const paths = [...fields].map((field) => field.getAttribute('data-path'));
    expect(paths).toEqual(['policies.observation.paused']);
  });

  it('leaves the editor out, keeping the read-only rows, for a viewer who may not write', async () => {
    serveWithObservationConfig(
      { values: { policies: { observation: { paused: false } } } },
      principalHolding(['config.read']),
    );

    render(await AlertIntakeScreen(await surfaceContext({})));

    expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('effective-field').length).toBeGreaterThan(0);
  });

  // The bridge's own lists and the detector list have no purpose-built
  // add/remove/reorder control of their own — they draw through this same
  // prefixed `ConfigEditor` as an `ObjectList`, the moment the schema
  // describes what one entry looks like. This is the proof that they do,
  // pinning the capability rather than a purpose-built screen for it.
  const OBSERVATION_LIST_PATHS = [
    'policies.observation.detectors',
    'policies.observation.bridge.dashboards',
    'policies.observation.bridge.label_rules',
    'policies.observation.bridge.log_selectors',
    'policies.observation.bridge.precedence',
    'policies.observation.guardian.overrides',
  ] as const;

  function listField(path: string): unknown {
    return {
      path,
      label: path,
      type: 'array',
      section: 'Observation',
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
    };
  }

  it('draws every observation list — the detector set and the bridge’s own — as an editable, reorderable list', async () => {
    serveWithObservationConfig({
      values: { policies: { observation: {} } },
      fields: OBSERVATION_LIST_PATHS.map((path) => listField(path)),
    });

    render(await AlertIntakeScreen(await surfaceContext({})));

    const section = screen.getByTestId('advanced-config-policies-observation');
    for (const path of OBSERVATION_LIST_PATHS) {
      const field = section.querySelector(
        `[data-testid="config-field"][data-path="${path}"]`,
      );
      expect(field).not.toBeNull();
      expect(field?.querySelector('[data-testid="object-list"]')).toBeInTheDocument();
    }
  });
});

/** The chain node addressed as `role` — narrowed by failing the test rather than by asserting. */
function requireChainNode(role: string): HTMLElement {
  const node = screen
    .getAllByTestId('chain-node')
    .find((candidate) => candidate.getAttribute('data-role') === role);
  if (node === undefined) throw new Error(`no chain node for role ${role}`);
  return node;
}

/** The `href` of the one link inside `node` — narrowed the same way. */
function chainNodeHref(node: HTMLElement): string {
  return within(node).getByRole('link').getAttribute('href') ?? '';
}

describe('the chain: intake, rule, action and destination', () => {
  it('renders four nodes in order, each naming this deployment’s own value', async () => {
    await page();

    const nodes = screen.getAllByTestId('chain-node');
    expect(nodes).toHaveLength(4);
    expect(nodes.map((node) => node.getAttribute('data-role'))).toEqual([
      'intake',
      'rule',
      'action',
      'destination',
    ]);

    expect(requireChainNode('intake')).toHaveTextContent('alertmanager');
    expect(requireChainNode('rule')).toHaveTextContent('critical-to-platform');
    expect(requireChainNode('action')).toHaveTextContent('investigate');
    expect(requireChainNode('destination')).toHaveTextContent('chat-incidents');
  });

  it('the rule node names a rule the routing-rules panel actually lists, not a value this test invented', async () => {
    await page();

    const ruleText = requireChainNode('rule').textContent.trim();
    const combined = [
      ...screen.getAllByTestId('routing-rule'),
      ...screen.getAllByTestId('catch-all-rule'),
    ]
      .map((row) => row.textContent)
      .join(' | ');

    expect(ruleText).not.toBe('');
    expect(combined).toContain(ruleText);
  });

  it('picks the first destination this deployment can actually deliver to, skipping one it cannot', async () => {
    serveScenario('populated');
    const base = globalThis.fetch;
    vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
      const path = new URL(String(input), FIXTURE_BASE).pathname;
      if (path !== '/v1/transit/destinations') return base(input as string, init);
      const response = await base(input as string, init);
      const body = (await response.json()) as {
        readonly destinations: readonly Record<string, unknown>[];
      };
      // The unconfigurable destination first, so a chain that just took row
      // zero without reading `unconfigurable_reason` would name it instead.
      return new Response(
        JSON.stringify({ ...body, destinations: [...body.destinations].reverse() }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      );
    });

    render(await AlertIntakeScreen(await surfaceContext({})));

    expect(requireChainNode('destination')).toHaveTextContent('chat-incidents');
  });

  it('each node links to the screen that owns its setting', async () => {
    await page();

    expect(chainNodeHref(requireChainNode('intake'))).toBe('/integrations');
    expect(chainNodeHref(requireChainNode('rule'))).toBe(
      '/settings/schedules-destinations#advanced-config-transit',
    );
    expect(chainNodeHref(requireChainNode('action'))).toBe(
      '/settings/schedules-destinations#advanced-config-transit',
    );
    expect(chainNodeHref(requireChainNode('destination'))).toBe(
      '/settings/schedules-destinations#advanced-config-transit',
    );
  });

  it('still shows four nodes, naming what is missing, when the deployment has configured no rule', async () => {
    serveScenario('populated');
    const base = globalThis.fetch;
    vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
      const path = new URL(String(input), FIXTURE_BASE).pathname;
      if (path !== '/v1/transit/rules') return base(input as string, init);
      return new Response(JSON.stringify({ rules: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    });

    render(await AlertIntakeScreen(await surfaceContext({})));

    expect(screen.getAllByTestId('chain-node')).toHaveLength(4);
    expect(requireChainNode('rule')).toHaveTextContent('No rule is configured yet');
    expect(requireChainNode('action')).toHaveTextContent('No action runs yet');
    // Unconfigured is still a link to where it gets configured, never a dead label.
    expect(chainNodeHref(requireChainNode('rule'))).toBe(
      '/settings/schedules-destinations#advanced-config-transit',
    );
  });

  it('still shows four nodes, naming what is missing, on a deployment that has configured nothing', async () => {
    await page('empty');

    expect(screen.getAllByTestId('chain-node')).toHaveLength(4);
    expect(requireChainNode('intake')).toHaveTextContent('No source has delivered yet');
    expect(requireChainNode('destination')).toHaveTextContent(
      'No destination is configured yet',
    );
    // The gateway's own default catch-all is still a real decision, not an
    // absence — the empty scenario configures nothing beyond it.
    expect(requireChainNode('rule')).toHaveTextContent('catch-all');
    expect(requireChainNode('action')).toHaveTextContent('investigate');
  });

  it('does not disappear when the routing-rules read itself fails', async () => {
    serveScenarioExcept('populated', ['/v1/transit/rules']);
    render(await AlertIntakeScreen(await surfaceContext({})));

    // The rules panel goes to its own error state; the chain, deliberately
    // outside it, still names all four nodes.
    expect(
      screen
        .getAllByTestId('panel')
        .filter((panel) => panel.getAttribute('data-state') === 'error'),
    ).toHaveLength(1);
    expect(screen.getAllByTestId('chain-node')).toHaveLength(4);
  });
});
