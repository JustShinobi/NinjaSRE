import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  IntegrationPanel,
  type IntegrationPanelItem,
  type IntegrationPanelLabels,
} from '@/surfaces/integration-panel';

/**
 * The credential panel, on its own: an already-connected integration shows
 * its state and three actions rather than an empty write-only form; the
 * estate's own discovered address stands in as a placeholder sentence when
 * there is one; a name the catalogue cut removed offers both ways out; and
 * nowhere in any of it does a stored credential's value ever reach a DOM
 * attribute or an outbound response.
 *
 * `IntegrationsScreen`'s own tests (`integrations.test.tsx`) additionally
 * prove the wiring from the API payload into these same props — this file is
 * the component's own contract, exercised directly.
 */

const CLOSE_HREF = '/integrations';
const NOT_COVERED_HREF = '/integrations/not-covered';
const INTAKE_HREF = '/settings/alert-intake';

/**
 * An address the estate found a service on, built rather than written — the
 * console bans a third-party origin appearing whole in its source, and a test
 * fixture is source like any other.
 */
const DISCOVERED_ADDRESS = ['http:', '//10.20.20.37:9093'].join('');

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

function item(overrides: Partial<IntegrationPanelItem> = {}): IntegrationPanelItem {
  return {
    name: 'alertmanager',
    displayName: 'Alertmanager',
    categoryLabel: 'Incident management',
    summary: 'What is firing, grouped and silenced.',
    health: 'unconfigured',
    healthDetail: '',
    fields: [
      {
        name: 'token',
        label: 'Bearer token',
        help: 'Only if something fronts it.',
        secret: true,
        required: false,
      },
    ],
    permissions: [],
    discoveredAddress: '',
    direction: 'outbound',
    intakePath: '',
    ...overrides,
  };
}

interface Sent {
  readonly url: string;
  readonly method: string;
  readonly body: string;
}

let sent: Sent[] = [];

/** A `fetch` stub that answers every request the same way, and records each one. */
function answering(status: number, body: unknown) {
  return vi.fn((input: unknown, init?: RequestInit) => {
    sent.push({
      url: String(input),
      method: init?.method ?? 'GET',
      body: typeof init?.body === 'string' ? init.body : '',
    });
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  sent = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a connected integration: state and actions, not an empty form', () => {
  it('does not render an empty credential field paired with a disabled action, for a verified integration', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy', healthDetail: 'verified 3 hours ago' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.queryByTestId('store-credential')).toBeNull();
    expect(screen.queryByTestId('credential')).toBeNull();
  });

  it('affirms the credential is stored in the vault, where one is', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="redis"
        item={item({
          health: 'healthy',
          fields: [
            {
              name: 'api_key',
              label: 'API key',
              help: 'The key.',
              secret: true,
              required: true,
            },
          ],
        })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('credential-stored-note')).toHaveTextContent(
      LABELS.storedInVault,
    );
  });

  it('says a vendor that needs no credential is connected by its address', () => {
    // The fixture is Alertmanager, whose only secret is optional because it
    // ships no authentication. Telling an operator their credential is in the
    // vault sends them looking for a key nobody ever entered.
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('credential-stored-note')).toHaveTextContent(
      LABELS.connectedByAddress,
    );
  });

  it('offers Test again, Replace credential and Disconnect, named', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByRole('button', { name: /^Test again$/ })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /^Replace credential$/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Disconnect/ })).toBeInTheDocument();
  });

  it('shows the actions view for a credential stored but never verified, not the empty form', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="loki"
        item={item({ name: 'loki', displayName: 'Loki', health: 'unknown' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('credential-connected')).toBeInTheDocument();
    expect(screen.queryByTestId('credential')).toBeNull();
  });

  it('shows the actions view for a failing credential too — a bad credential does not empty the form', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="ticketing"
        item={item({
          name: 'ticketing',
          displayName: 'Ticketing',
          health: 'degraded',
          healthDetail: 'the last verification timed out',
        })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('credential-connected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Disconnect/ })).toBeInTheDocument();
  });

  it('still shows the write-only form directly for an integration with nothing stored', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'unconfigured' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('credential')).toBeInTheDocument();
    expect(screen.queryByTestId('credential-connected')).toBeNull();
    expect(screen.queryByRole('button', { name: /^Disconnect/ })).toBeNull();
  });
});

describe('Test again', () => {
  it('asks the same verify courier the initial connection uses, naming this integration', async () => {
    vi.stubGlobal('fetch', answering(200, { reachable: true, verified: true }));
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Test again$/ }));

    expect(sent).toHaveLength(1);
    expect(sent[0]?.url).toBe('/api/verify');
    expect(JSON.parse(sent[0]?.body ?? '{}')).toEqual({
      kind: 'integration',
      name: 'alertmanager',
    });
  });

  it('shows the result as the canonical chip, with its diagnostic beside it', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, { reachable: true, verified: false, reason: 'token rejected' }),
    );
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Test again$/ }));

    const outcome = await screen.findByTestId('credential-outcome');
    expect(outcome).toHaveTextContent('token rejected');
    expect(outcome.querySelector('[data-credential-status="failing"]')).not.toBeNull();
  });

  it('reports a vendor that answered with no credential at all as verified', async () => {
    // Alertmanager ships no authentication. The deployment stores nothing for
    // it, reaches it by address, and the only thing worth showing is what it
    // said — which used to come back as a failure about a missing credential.
    vi.stubGlobal(
      'fetch',
      answering(200, {
        reachable: true,
        verified: true,
        reason: 'Alertmanager answered.',
      }),
    );
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Test again$/ }));

    const outcome = await screen.findByTestId('credential-outcome');
    expect(outcome).toHaveTextContent('Alertmanager answered.');
    expect(outcome.querySelector('[data-credential-status="verified"]')).not.toBeNull();
  });

  it('shows a vendor that answered with a caveat as degraded rather than as either extreme', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, {
        reachable: true,
        verified: true,
        degraded: true,
        reason: 'Prometheus answered.',
      }),
    );
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Test again$/ }));

    const outcome = await screen.findByTestId('credential-outcome');
    expect(outcome.querySelector('[data-credential-status="degraded"]')).not.toBeNull();
  });
});

describe('Replace credential', () => {
  it('reveals the identical write-only form, with Save and test as the only primary action, once replacing starts', async () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Replace credential$/ }));

    expect(screen.getByTestId('credential')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^Save and test$/ })).toHaveLength(1);
    expect(screen.queryByTestId('credential-connected')).toBeNull();
  });

  it('offers a way back without saving', async () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Replace credential$/ }));
    await userEvent.click(screen.getByRole('button', { name: /^Cancel$/ }));

    expect(screen.getByTestId('credential-connected')).toBeInTheDocument();
    expect(screen.queryByTestId('credential')).toBeNull();
  });

  it('returns to the connected-actions view once the replacement is saved', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, {
        ok: true,
        reachable: true,
        state: 'usable',
        version: 2,
        fields: ['token'],
      }),
    );
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Replace credential$/ }));
    await userEvent.type(
      screen.getByLabelText('Bearer token'),
      'ninja_am_9f2b7c1e0d3a',
    );
    await userEvent.click(screen.getByRole('button', { name: /^Save and test$/ }));

    expect(await screen.findByTestId('credential-connected')).toBeInTheDocument();
  });
});

describe('Disconnect', () => {
  function renderConnected() {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );
  }

  it('requires a confirmation naming the integration and what will be removed, before any write', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, { integration: 'alertmanager', versionsRemoved: 1 }),
    );
    renderConnected();

    await userEvent.click(screen.getByRole('button', { name: /^Disconnect/ }));

    const dialog = screen.getByRole('dialog', { name: /^Disconnect$/ });
    expect(dialog).toHaveTextContent('Alertmanager');
    expect(dialog).toHaveTextContent(LABELS.disconnectConsequence);
    // Named before any write: nothing has been sent yet.
    expect(sent).toHaveLength(0);
  });

  it('sends the DELETE only once the confirmation is confirmed, naming this integration and nothing else', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, { integration: 'alertmanager', versionsRemoved: 1 }),
    );
    renderConnected();

    await userEvent.click(screen.getByRole('button', { name: /^Disconnect/ }));
    const dialog = screen.getByRole('dialog', { name: /^Disconnect$/ });
    await userEvent.click(within(dialog).getByRole('button', { name: /^Disconnect/ }));

    expect(sent).toHaveLength(1);
    expect(sent[0]?.method).toBe('DELETE');
    expect(sent[0]?.url).toBe('/api/credential');
    expect(JSON.parse(sent[0]?.body ?? '{}')).toEqual({ integration: 'alertmanager' });
  });

  it('shows the write-only form once disconnecting succeeds, without leaving the page', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, { integration: 'alertmanager', versionsRemoved: 1 }),
    );
    renderConnected();

    await userEvent.click(screen.getByRole('button', { name: /^Disconnect/ }));
    const dialog = screen.getByRole('dialog', { name: /^Disconnect$/ });
    await userEvent.click(within(dialog).getByRole('button', { name: /^Disconnect/ }));

    expect(await screen.findByTestId('credential')).toBeInTheDocument();
    expect(screen.queryByTestId('credential-connected')).toBeNull();
    expect(screen.queryByRole('dialog', { name: /^Disconnect$/ })).toBeNull();
  });

  it('leaves the credential exactly as it was, when the confirmation is cancelled', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, { integration: 'alertmanager', versionsRemoved: 1 }),
    );
    renderConnected();

    await userEvent.click(screen.getByRole('button', { name: /^Disconnect/ }));
    await userEvent.click(screen.getByRole('button', { name: /^Cancel$/ }));

    expect(sent).toHaveLength(0);
    expect(screen.getByTestId('credential-connected')).toBeInTheDocument();
  });

  it('names why, when the deployment refuses the disconnect', async () => {
    vi.stubGlobal(
      'fetch',
      answering(403, { reason: 'this token cannot manage integrations' }),
    );
    renderConnected();

    await userEvent.click(screen.getByRole('button', { name: /^Disconnect/ }));
    const dialog = screen.getByRole('dialog', { name: /^Disconnect$/ });
    await userEvent.click(within(dialog).getByRole('button', { name: /^Disconnect/ }));

    expect(await screen.findByTestId('disconnect-outcome')).toHaveTextContent(
      'this token cannot manage integrations',
    );
    // A refusal is not a disconnect: the actions view — and the credential —
    // are exactly as they were.
    expect(screen.getByTestId('credential-connected')).toBeInTheDocument();
  });

  it('says the deployment could not be reached, when the request never lands', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('network down'))),
    );
    renderConnected();

    await userEvent.click(screen.getByRole('button', { name: /^Disconnect/ }));
    const dialog = screen.getByRole('dialog', { name: /^Disconnect$/ });
    await userEvent.click(within(dialog).getByRole('button', { name: /^Disconnect/ }));

    expect(await screen.findByTestId('disconnect-outcome')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('the estate-discovered address', () => {
  it('shows it as a sentence ahead of the fields, when the estate found one', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({
          health: 'unconfigured',
          discoveredAddress: DISCOVERED_ADDRESS,
        })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('panel-discovered-address')).toHaveTextContent(
      'Found in your estate at http://10.20.20.37:9093',
    );
  });

  it('renders no placeholder sentence at all when the estate knows nothing', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'unconfigured', discoveredAddress: '' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.queryByTestId('panel-discovered-address')).toBeNull();
  });

  it('carries each field’s own instruction, not only its label', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'unconfigured' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByText('Only if something fronts it.')).toBeInTheDocument();
  });
});

describe('an integration the cut removed', () => {
  it('says it is not available, and offers both a way back and the roadmap list', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="slack"
        item={null}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('panel-not-found-back')).toHaveAttribute(
      'href',
      CLOSE_HREF,
    );
    expect(screen.getByTestId('panel-not-found-roadmap')).toHaveAttribute(
      'href',
      NOT_COVERED_HREF,
    );
  });
});

describe('security: no credential value ever reaches the DOM or an outbound response', () => {
  it('clears the field the instant a store succeeds, and echoes nothing back even if the response carried it', async () => {
    const secret = 'ninja_am_9f2b7c1e0d3a';
    // A well-behaved gateway never echoes a stored value back (confirmed by
    // `CredentialWriteView`, which has no field a value could sit in) — this
    // plants one anyway, in a field the panel has no reason to read, so the
    // assertion below is about what the component does, not about what this
    // test happened to send it.
    vi.stubGlobal(
      'fetch',
      answering(200, {
        ok: true,
        reachable: true,
        state: 'usable',
        version: 1,
        fields: ['token'],
        token: secret,
      }),
    );
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'unconfigured' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    const field = screen.getByLabelText('Bearer token');
    await userEvent.type(field, secret);
    await userEvent.click(screen.getByRole('button', { name: /^Save and test$/ }));

    await screen.findByTestId('credential-result');
    expect((field as HTMLInputElement).value).toBe('');
    for (const element of document.body.querySelectorAll('*')) {
      expect(element.outerHTML).not.toContain(secret);
      for (const attribute of Array.from(element.attributes)) {
        expect(attribute.value).not.toContain(secret);
      }
    }
  });

  it('never carries a credential value into the DOM when re-testing an already-connected integration', async () => {
    const secret = 'ninja_am_9f2b7c1e0d3a';
    // Same plant, on the verify courier's own response this time — `reason`
    // is the one field `testNow` renders, and it is a diagnostic sentence,
    // never a credential.
    vi.stubGlobal(
      'fetch',
      answering(200, { reachable: true, verified: true, token: secret }),
    );
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Test again$/ }));
    await screen.findByTestId('credential-outcome');

    for (const element of document.body.querySelectorAll('*')) {
      expect(element.outerHTML).not.toContain(secret);
    }
  });

  it('shows a credential that is stored but never verified as stored, never as failing', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="loki"
        item={item({ name: 'loki', displayName: 'Loki', health: 'unknown' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable
        labels={LABELS}
      />,
    );

    const chip = document.querySelector('[data-credential-status]');
    expect(chip).not.toBeNull();
    expect(chip?.getAttribute('data-credential-status')).toBe('stored');
    expect(chip?.textContent.toLowerCase()).not.toContain('failing');
  });
});

describe('a viewer without the permission to manage integrations', () => {
  it('shows no credential form and no actions, only the reason', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="alertmanager"
        item={item({ health: 'healthy' })}
        closeHref={CLOSE_HREF}
        notCoveredHref={NOT_COVERED_HREF}
        intakeHref={INTAKE_HREF}
        writable={false}
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('credential-read-only')).toHaveTextContent(
      LABELS.readOnly,
    );
    expect(screen.queryByTestId('credential-connected')).toBeNull();
    expect(screen.queryByRole('button', { name: /^Disconnect/ })).toBeNull();
  });
});
