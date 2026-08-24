import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  IntegrationPanel,
  type IntegrationPanelItem,
  type IntegrationPanelLabels,
} from '@/surfaces/integration-panel';

/**
 * What the panel shows when the deployment refused a certificate.
 *
 * The defect this covers: a self-signed hypervisor — the default install, not
 * an eccentricity — reported as "no node answered", which sends an operator to
 * check a network that is fine. They check it, find it correct, and conclude
 * the product is broken.
 *
 * The sentence is the **server's**, not a catalogue string, and that is the
 * design rather than an omission. Only the server knows which certificate was
 * presented and which was expected, and a fixed phrase here would either drop
 * those two facts or paraphrase them into something an operator cannot compare
 * against what the node shows. So there is no message key for this, and these
 * tests hold the panel to passing the server's words through untouched.
 */

const CLOSE_HREF = '/integrations';
const NOT_COVERED_HREF = '/integrations/not-covered';
const INTAKE_HREF = '/settings/alert-intake';

/** A SHA-256 fingerprint the way a management interface prints one. */
const OBSERVED = [
  'AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77',
  '88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99',
].join(':');
const EXPECTED = [
  '11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE',
  'FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00',
].join(':');

/** The sentence a genuinely silent host produces, and the one that must not appear. */
const SILENT_HOST =
  'Neither the credential proxy nor any configured Proxmox node answered.';

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
  disconnectConsequence:
    'This removes the stored credential from the vault. The integration returns to Available until it is reconnected.',
  directionOutbound: 'This deployment calls it. Nothing arrives from it.',
  directionBoth: 'Both ways. It also posts alerts here.',
  intakeTitle: 'Where to send alerts',
  intakeBody: 'The one step that happens outside this deployment.',
  intakeAction: 'Point your alert router at it',
};

function connected(): IntegrationPanelItem {
  return {
    name: 'proxmox',
    displayName: 'Proxmox VE',
    categoryLabel: 'Virtualisation',
    summary: 'Nodes, guests and datastores.',
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

/** A `fetch` stub answering the verify courier with one verdict. */
function verdictOf(reason: string) {
  return vi.fn(() =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          ok: false,
          reachable: true,
          verified: false,
          degraded: false,
          reason,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    ),
  );
}

async function testAgainShowing(reason: string): Promise<string> {
  vi.stubGlobal('fetch', verdictOf(reason));
  render(
    <IntegrationPanel
      locale="en"
      requestedName="proxmox"
      item={connected()}
      closeHref={CLOSE_HREF}
      notCoveredHref={NOT_COVERED_HREF}
      intakeHref={INTAKE_HREF}
      writable
      labels={LABELS}
    />,
  );

  await userEvent.click(screen.getByTestId('test-again'));
  await waitFor(() => {
    expect(screen.getByTestId('credential-outcome')).toBeTruthy();
  });
  return screen.getByTestId('credential-outcome').textContent ?? '';
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the refusal the panel shows is the one that actually happened', () => {
  it('shows the fingerprint the address presented, rather than a network complaint', async () => {
    const shown = await testAgainShowing(
      `10.20.20.9 presented a certificate this deployment has no reason to trust, so nothing was sent. Its SHA-256 fingerprint is ${OBSERVED}.`,
    );

    expect(shown).toContain(OBSERVED);
    expect(shown).not.toContain(SILENT_HOST);
  });

  it('shows both fingerprints when a pin was broken', async () => {
    const shown = await testAgainShowing(
      `10.20.20.9 presented a certificate that is not pinned for it, so nothing was sent. Expected ${EXPECTED}; observed ${OBSERVED}.`,
    );

    expect(shown).toContain(EXPECTED);
    expect(shown).toContain(OBSERVED);
    expect(shown).not.toContain(SILENT_HOST);
  });

  it('shows the address and the name the certificate carries when they disagree', async () => {
    const shown = await testAgainShowing(
      'The certificate 10.20.20.9 presented is trusted but it does not name 10.20.20.9. It names pve02.lan.example.',
    );

    expect(shown).toContain('10.20.20.9');
    expect(shown).toContain('pve02.lan.example');
    expect(shown).not.toContain(SILENT_HOST);
  });

  it('still shows the network sentence when the host genuinely did not answer', async () => {
    const shown = await testAgainShowing(SILENT_HOST);

    expect(shown).toContain(SILENT_HOST);
    expect(shown.toLowerCase()).not.toContain('fingerprint');
  });

  it('passes the sentence through rather than substituting one of its own', async () => {
    // The point of the whole file: no catalogue string stands in for this, so
    // there is no key that could go stale against what the server sends.
    const shown = await testAgainShowing(`observed ${OBSERVED}`);

    expect(shown).toContain(OBSERVED);
  });
});
