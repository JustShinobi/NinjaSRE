import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { IntegrationPanelItem } from '@/surfaces/integration-panel';
import { IntegrationPanel } from '@/surfaces/integration-panel';
import type { IntegrationOffer } from '@/surfaces/first-run/integrations';
import { IntegrationsStep } from '@/surfaces/first-run/integrations';

/**
 * The one fact this suite exists to prove: the slide-over that asks for a
 * vendor's credential and the guided first run that asks for the same
 * vendor's credential show the identical sentence about where to obtain it.
 *
 * Both surfaces read from one declaration on the deployment side — the
 * vendor's own profile — so a divergence here can only mean one of the two
 * screens started carrying a copy rather than a read.
 */

const PHRASE =
  "Create a service account token from Grafana's own Administration → Service accounts screen, with the Viewer role.";

const CREDENTIAL_LABELS = {
  submit: 'Store',
  sending: 'Storing…',
  stored: 'stored',
  absent: 'This integration has no credential fields.',
  whereToGetIt: 'Where to get it:',
  required: 'required',
  saved: 'Saved.',
  refused: 'Refused.',
  unreachable: 'Could not reach the deployment.',
  minScope: 'Minimum permission:',
  guide: 'Guide',
};

function panelItem(): IntegrationPanelItem {
  return {
    name: 'grafana',
    displayName: 'Grafana',
    categoryLabel: 'Cloud control plane',
    summary: 'Dashboards, folders, and the annotation timeline.',
    health: 'unconfigured',
    healthDetail: '',
    credentialTeamAmbiguous: false,
    fields: [
      {
        name: 'token',
        label: 'Service account token',
        help: '',
        secret: true,
        required: true,
        minScope: 'Viewer role',
      },
    ],
    permissions: [],
    discoveredAddress: '',
    direction: 'outbound',
    intakePath: '',
    whereToGetIt: PHRASE,
    docsMarkdown: '',
    docsReadable: true,
  };
}

function offer(): IntegrationOffer {
  return {
    name: 'grafana',
    displayName: 'Grafana',
    summary: 'Dashboards, folders, and the annotation timeline.',
    category: 'cloud_control_plane',
    fields: [
      {
        name: 'token',
        label: 'Service account token',
        help: '',
        secret: true,
        required: true,
        minScope: 'Viewer role',
      },
    ],
    configured: false,
    whereToGetIt: PHRASE,
  };
}

describe('the same phrase reaches both screens that ask for a credential', () => {
  it('is character for character identical on the integration panel and the first-run step', () => {
    render(
      <IntegrationPanel
        locale="en"
        requestedName="grafana"
        item={panelItem()}
        closeHref="/integrations"
        notCoveredHref="/integrations/not-covered"
        intakeHref="/settings/alert-intake"
        writable
        labels={{
          close: 'Close',
          credential: CREDENTIAL_LABELS,
          security: 'Never leaves the vault.',
          notFound: 'Not found',
          notFoundAction: 'Back to the catalogue',
          notFoundRoadmap: 'See the roadmap',
          testing: 'Testing…',
          unreachable: 'Could not reach the deployment.',
          readOnly: 'Read only.',
          permissionsHeading: 'Permissions',
          grantedAt: 'Granted at',
          foundHere: 'Found in your estate at',
          storedInVault: 'Stored in the vault.',
          connectedByAddress: 'Connected by the address above.',
          testAgain: 'Test again',
          replaceCredential: 'Replace credential',
          cancel: 'Cancel',
          disconnect: 'Disconnect',
          disconnectConsequence: 'Removes the stored credential.',
          directionOutbound: 'This deployment calls it.',
          directionBoth: 'Both ways.',
          intakeTitle: 'Where to send alerts',
          intakeBody: 'The one step outside this deployment.',
          intakeAction: 'Point your alert router at it',
          docsHeading: 'Package documentation',
          docsToggle: 'Read the package documentation',
          docsUnreadable: "This vendor's own documentation could not be read.",
          credentialTeamAmbiguous: "More than one team holds a credential for this vendor.",
        }}
      />,
    );
    const fromPanel = screen.getByTestId('where-to-get-it').textContent;

    const { container } = render(
      <IntegrationsStep
        offers={[offer()]}
        labels={{
          search: 'Search',
          none: 'Nothing matches.',
          connected: 'Connected',
          notConnected: 'Not connected',
          optional: 'Every integration here is optional.',
          summary: 'Connected: {names}.',
          summaryNone: 'Nothing connected yet.',
          failed: 'failed:',
          foundHere: 'Found in your estate at',
          credential: CREDENTIAL_LABELS,
        }}
      />,
    );
    const offerRow = container.querySelector('[data-integration="grafana"]');
    expect(offerRow).not.toBeNull();
    const fromFirstRun = within(offerRow as HTMLElement).getByTestId(
      'where-to-get-it',
    ).textContent;

    expect(fromPanel).toContain(PHRASE);
    expect(fromFirstRun).toContain(PHRASE);
    // Strip each screen's own label prefix — the sentence after it is what
    // has to match; the two screens are not required to introduce it with
    // the same words.
    expect(fromPanel.replace(CREDENTIAL_LABELS.whereToGetIt, '').trim()).toBe(
      fromFirstRun.replace(CREDENTIAL_LABELS.whereToGetIt, '').trim(),
    );
  });
});
