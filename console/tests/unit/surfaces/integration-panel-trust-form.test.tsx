import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  IntegrationPanel,
  TRUST_ENDPOINT,
  type IntegrationPanelItem,
  type IntegrationPanelLabels,
} from '@/surfaces/integration-panel';
import { VERIFY_ENDPOINT } from '@/surfaces/first-run/verify';

/**
 * The write path onto certificate trust: declaring a pinned fingerprint or a
 * certificate authority for this integration's address, and — only for a
 * viewer who holds the dedicated permission — accepting one unverified.
 *
 * The panel already shows the *refusal* the server produced, verbatim
 * (`integration-panel-certificate.test.tsx`); this file is the other half,
 * the form that lets an operator declare trust from the screen instead of
 * calling the API directly. Every field goes through the panel's existing
 * declared-field controls (`Input`/`Textarea`), so there is no new component
 * here — only new state, a new courier, and a permission gate.
 */

const CLOSE_HREF = '/integrations';
const NOT_COVERED_HREF = '/integrations/not-covered';
const INTAKE_HREF = '/settings/alert-intake';

const FINGERPRINT_A =
  'AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99';
const FINGERPRINT_B =
  '11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00';

const LABELS: IntegrationPanelLabels = {
  close: 'Close',
  credential: {
    submit: 'Save and test',
    sending: 'Saving and testing…',
    stored: 'A credential is already stored.',
    absent: 'No fields are declared.',
    whereToGetIt: 'Get it from',
    required: 'Required fields are missing.',
    saved: 'Saved.',
    refused: 'The deployment refused it:',
    unreachable: 'The deployment could not be reached.',
    minScope: 'Minimum scope:',
    guide: 'Guide',
  },
  security: 'Stored in the vault; never shown again.',
  notFound: 'This integration is not in the catalogue.',
  notFoundAction: 'Back to Integrations',
  notFoundRoadmap: 'Not covered, and why',
  testing: 'Saving and testing…',
  unreachable: 'The deployment could not be reached.',
  readOnly: 'You do not hold the permission to change this integration.',
  permissionsHeading: 'Required permissions',
  grantedAt: 'Granted at',
  foundHere: 'Found in your estate at',
  storedInVault: 'This credential is stored in the vault.',
  connectedByAddress: 'Connected by the address above.',
  testAgain: 'Test again',
  replaceCredential: 'Replace credential',
  cancel: 'Cancel',
  disconnect: 'Disconnect',
  disconnectConsequence: 'This removes the stored credential from the vault.',
  directionOutbound: 'This deployment calls it. Nothing arrives from it.',
  directionBoth: 'Both ways. It also posts alerts here.',
  intakeTitle: 'Where to send alerts',
  intakeBody: 'The one step that happens outside this deployment.',
  intakeAction: 'Point your alert router at it',
  docsHeading: 'Package documentation',
  docsToggle: 'Read the package documentation',
  docsUnreadable: "This vendor's own documentation could not be read.",
  trust: {
    heading: 'Certificate trust',
    intro: 'What this deployment accepts from the certificate this address presents.',
    fingerprintsLabel: 'Pinned fingerprints',
    fingerprintsHelp: 'One SHA-256 fingerprint per line.',
    certificateLabel: 'Certificate authority (PEM)',
    certificateHelp: 'The authority the cluster minted for itself.',
    submit: 'Declare trust',
    sending: 'Declaring…',
    saved: 'Declared. Testing the connection now.',
    refused: 'The deployment refused it:',
    unreachable: 'The deployment could not be reached.',
    unverifiedHeading: 'Accept without verifying',
    unverifiedReasonLabel: 'Why',
    unverifiedReasonHelp: 'Recorded with your name and the moment you accept.',
  },
};

function connected(): IntegrationPanelItem {
  return {
    name: 'proxmox',
    displayName: 'Proxmox VE',
    categoryLabel: 'Virtualisation',
    summary: 'Nodes, guests and datastores.',
    docsMarkdown: '',
    docsReadable: false,
    health: 'degraded',
    healthDetail: '',
    fields: [
      {
        name: 'api_token',
        label: 'API token',
        help: 'user@realm!tokenid=secret',
        secret: true,
        required: true,
      },
    ],
    permissions: [],
    discoveredAddress: '',
    direction: 'outbound',
    intakePath: '',
    whereToGetIt: '',
  };
}

/** A `fetch` stub that answers by URL, and records every call it saw. */
function routed(
  handlers: Readonly<Record<string, () => Response>>,
): [typeof fetch, () => readonly [string, RequestInit][]] {
  const calls: [string, RequestInit][] = [];
  const fetching = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    calls.push([url, init ?? {}]);
    const handler = handlers[url];
    if (handler === undefined) {
      throw new Error(`this test's fetch stub was not told what ${url} answers`);
    }
    return Promise.resolve(handler());
  });
  return [fetching, () => calls];
}

function ok(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function refused(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function renderPanel(mayTrustUnverified: boolean): void {
  render(
    <IntegrationPanel
      locale="en"
      requestedName="proxmox"
      item={connected()}
      closeHref={CLOSE_HREF}
      notCoveredHref={NOT_COVERED_HREF}
      intakeHref={INTAKE_HREF}
      writable
      mayTrustUnverified={mayTrustUnverified}
      labels={LABELS}
    />,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the fields, through the panel’s own controls — no new component, no checkbox', () => {
  it('shows the fingerprint and certificate fields for any writable viewer', () => {
    vi.stubGlobal('fetch', routed({})[0]);
    renderPanel(false);

    expect(screen.getByLabelText('Pinned fingerprints')).toBeTruthy();
    expect(screen.getByLabelText('Certificate authority (PEM)')).toBeTruthy();
  });

  it('is never a checkbox anywhere in the certificate trust group', () => {
    vi.stubGlobal('fetch', routed({})[0]);
    renderPanel(true);

    const group = screen.getByTestId('certificate-trust');
    expect(group.querySelectorAll('input[type="checkbox"]')).toHaveLength(0);
  });

  it('does not show accepting unverified as available without the permission', () => {
    vi.stubGlobal('fetch', routed({})[0]);
    renderPanel(false);

    expect(screen.queryByTestId('trust-unverified')).toBeNull();
    expect(screen.queryByLabelText('Why')).toBeNull();
  });

  it('shows the reason field once the viewer holds the dedicated permission', () => {
    vi.stubGlobal('fetch', routed({})[0]);
    renderPanel(true);

    expect(screen.getByTestId('trust-unverified')).toBeTruthy();
    expect(screen.getByLabelText('Why')).toBeTruthy();
  });

  it('leaves the submit control disabled until something is declared', () => {
    vi.stubGlobal('fetch', routed({})[0]);
    renderPanel(true);

    expect(screen.getByTestId('trust-submit')).toBeDisabled();
  });

  it('does not let whitespace in the reason field stand in for a written one', () => {
    vi.stubGlobal('fetch', routed({})[0]);
    renderPanel(true);

    fireEvent.change(screen.getByLabelText('Why'), { target: { value: '   ' } });

    expect(screen.getByTestId('trust-submit')).toBeDisabled();
  });
});

describe('what a declaration sends', () => {
  it('splits fingerprints one per line and sends them as a set', async () => {
    const [fetching, callsOf] = routed({
      [TRUST_ENDPOINT]: () =>
        ok({ ok: true, anchor: 'pinned-fingerprint', addresses: ['10.20.20.9'] }),
      [VERIFY_ENDPOINT]: () => ok({ ok: true, verified: true }),
    });
    vi.stubGlobal('fetch', fetching);
    renderPanel(false);

    fireEvent.change(screen.getByLabelText('Pinned fingerprints'), {
      target: { value: `${FINGERPRINT_A}\n${FINGERPRINT_B}` },
    });
    await userEvent.click(screen.getByTestId('trust-submit'));

    await waitFor(() => {
      expect(callsOf().some(([url]) => url === TRUST_ENDPOINT)).toBe(true);
    });
    const [, init] = callsOf().find(([url]) => url === TRUST_ENDPOINT) ?? ['', {}];
    const sent: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    expect(Reflect.get(Object(sent), 'integration')).toBe('proxmox');
    expect(Reflect.get(Object(sent), 'fingerprints')).toEqual([
      FINGERPRINT_A,
      FINGERPRINT_B,
    ]);
    expect(Reflect.get(Object(sent), 'unverifiedReason')).toBe('');
  });

  it('never sends a reason when this viewer lacks the permission, even if the field somehow held one', async () => {
    const [fetching, callsOf] = routed({
      [TRUST_ENDPOINT]: () => ok({ ok: true }),
      [VERIFY_ENDPOINT]: () => ok({ ok: true, verified: true }),
    });
    vi.stubGlobal('fetch', fetching);
    renderPanel(false);

    fireEvent.change(screen.getByLabelText('Certificate authority (PEM)'), {
      target: { value: 'x' },
    });
    await userEvent.click(screen.getByTestId('trust-submit'));

    await waitFor(() => {
      expect(callsOf().some(([url]) => url === TRUST_ENDPOINT)).toBe(true);
    });
    const [, init] = callsOf().find(([url]) => url === TRUST_ENDPOINT) ?? ['', {}];
    const sent: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    expect(Reflect.get(Object(sent), 'unverifiedReason')).toBe('');
  });

  it('sends the reason once the permission is held and it is written', async () => {
    const [fetching, callsOf] = routed({
      [TRUST_ENDPOINT]: () => ok({ ok: true }),
      [VERIFY_ENDPOINT]: () => ok({ ok: true, verified: true }),
    });
    vi.stubGlobal('fetch', fetching);
    renderPanel(true);

    fireEvent.change(screen.getByLabelText('Why'), {
      target: { value: 'lab link with no DNS' },
    });
    await userEvent.click(screen.getByTestId('trust-submit'));

    await waitFor(() => {
      expect(callsOf().some(([url]) => url === TRUST_ENDPOINT)).toBe(true);
    });
    const [, init] = callsOf().find(([url]) => url === TRUST_ENDPOINT) ?? ['', {}];
    const sent: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    expect(Reflect.get(Object(sent), 'unverifiedReason')).toBe('lab link with no DNS');
  });

  it('re-tests the connection once a declaration is accepted, closing the loop in one click', async () => {
    const [fetching, callsOf] = routed({
      [TRUST_ENDPOINT]: () => ok({ ok: true, anchor: 'pinned-fingerprint' }),
      [VERIFY_ENDPOINT]: () =>
        ok({ ok: true, reachable: true, verified: true, reason: 'Proxmox answered.' }),
    });
    vi.stubGlobal('fetch', fetching);
    renderPanel(false);

    fireEvent.change(screen.getByLabelText('Pinned fingerprints'), {
      target: { value: FINGERPRINT_A },
    });
    await userEvent.click(screen.getByTestId('trust-submit'));

    await waitFor(() => {
      expect(callsOf().some(([url]) => url === VERIFY_ENDPOINT)).toBe(true);
    });
  });
});

describe('what a refusal shows', () => {
  it('shows the server’s own reason, naming the missing permission, unchanged', async () => {
    const message =
      "This action needs 'integration.trust_unverified' in this organisation. " +
      "The 'ADMIN' role grants it.";
    const [fetching] = routed({
      [TRUST_ENDPOINT]: () => refused(403, { ok: false, reachable: true, reason: message }),
    });
    vi.stubGlobal('fetch', fetching);
    renderPanel(true);

    fireEvent.change(screen.getByLabelText('Why'), {
      target: { value: 'lab link with no DNS' },
    });
    await userEvent.click(screen.getByTestId('trust-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('trust-result')).toBeTruthy();
    });
    expect(screen.getByTestId('trust-result').textContent).toContain(
      'integration.trust_unverified',
    );
  });

  it('says the deployment could not be reached, not that it refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('connect ECONNREFUSED'))),
    );
    renderPanel(false);

    fireEvent.change(screen.getByLabelText('Pinned fingerprints'), {
      target: { value: FINGERPRINT_A },
    });
    await userEvent.click(screen.getByTestId('trust-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('trust-result')).toBeTruthy();
    });
    expect(screen.getByTestId('trust-result').textContent).toBe(
      LABELS.trust.unreachable,
    );
  });
});

describe('a non-writable viewer', () => {
  it('sees no certificate trust group at all — absent, not disabled', () => {
    vi.stubGlobal('fetch', routed({})[0]);
    render(
      <IntegrationPanel
        locale="en"
        requestedName="proxmox"
        item={connected()}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable={false}
        mayTrustUnverified={false}
        labels={LABELS}
      />,
    );

    expect(screen.queryByTestId('certificate-trust')).toBeNull();
  });
});
