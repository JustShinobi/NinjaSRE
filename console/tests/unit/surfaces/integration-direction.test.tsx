import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  IntegrationPanel,
  type IntegrationPanelItem,
  type IntegrationPanelLabels,
} from '@/surfaces/integration-panel';

/**
 * The two questions the screen did not answer, asked of the component that owes
 * the answer.
 *
 * An operator opened Alertmanager, was asked for "Token", and had no way to
 * learn which token: the one stored here is outbound — this deployment
 * authenticating to the vendor — while the token that makes alerts *arrive* is
 * a delivery token issued elsewhere and held by the alert router. Two secrets,
 * one word, two screens, and no link between them.
 *
 * So the panel now states the direction, and for a vendor that also delivers it
 * says what remains to be done and where. The copy for that was already written
 * and referenced by nothing (`ingress.title` / `ingress.body`).
 */

const CLOSE_HREF = '/integrations';
const NOT_COVERED_HREF = '/integrations/not-covered';
const INTAKE_HREF = '/settings/alert-intake';

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
  directionBoth: 'Both ways. This deployment reads its API, and it posts alerts here.',
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
        name: 'endpoint',
        label: 'Alertmanager address',
        help: 'Where yours answers.',
        secret: false,
        required: true,
      },
    ],
    permissions: [],
    discoveredAddress: '',
    direction: 'outbound',
    intakePath: '',
    ...overrides,
  };
}

function panel(overrides: Partial<IntegrationPanelItem> = {}) {
  return render(
    <IntegrationPanel
      locale="en"
      requestedName="alertmanager"
      item={item(overrides)}
      closeHref={CLOSE_HREF}
      notCoveredHref={NOT_COVERED_HREF}
      intakeHref={INTAKE_HREF}
      labels={LABELS}
      writable
    />,
  );
}

describe('which way the traffic goes', () => {
  it('says a read-only vendor is only ever called, so nothing is waited for', () => {
    panel({ direction: 'outbound' });

    expect(screen.getByTestId('panel-direction')).toHaveTextContent(
      LABELS.directionOutbound,
    );
  });

  it('says a vendor that also delivers here goes both ways', () => {
    panel({ direction: 'both', intakePath: '/webhooks/alertmanager' });

    expect(screen.getByTestId('panel-direction')).toHaveTextContent(
      LABELS.directionBoth,
    );
  });
});

describe('what remains after the credential is stored', () => {
  it('tells an operator the step that happens outside this deployment, and links to it', () => {
    panel({ direction: 'both', intakePath: '/webhooks/alertmanager' });

    const next = screen.getByTestId('panel-intake-handover');
    expect(next).toHaveTextContent(LABELS.intakeTitle);
    expect(next).toHaveTextContent(LABELS.intakeBody);
    expect(screen.getByTestId('panel-intake-link')).toHaveAttribute(
      'href',
      INTAKE_HREF,
    );
  });

  it('names the path the alert router posts to, so it is not a second lookup', () => {
    panel({ direction: 'both', intakePath: '/webhooks/alertmanager' });

    expect(screen.getByTestId('panel-intake-handover')).toHaveTextContent(
      '/webhooks/alertmanager',
    );
  });

  it('offers no handover for a vendor that never delivers anything here', () => {
    panel({ direction: 'outbound' });

    expect(screen.queryByTestId('panel-intake-handover')).toBeNull();
  });

  it('still offers the handover once the credential is stored, which is when it is needed', () => {
    panel({
      direction: 'both',
      intakePath: '/webhooks/alertmanager',
      health: 'healthy',
    });

    expect(screen.getByTestId('panel-intake-handover')).toBeInTheDocument();
  });
});
