import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DecisionControls } from '@/surfaces/decision';
import { IncidentDecisionControls } from '@/surfaces/screens/incident-decision-controls';
import { DecisionCard, type DecisionCardProps } from '@/surfaces/proposal';

/**
 * The decision card: the artboard's anatomy, against the six sections and the
 * two live decide-in-place paths.
 *
 * `decisionFor` (`approvals.tsx`) composes `DecisionControls` when the
 * approval's run has an open interaction, and `IncidentDecisionControls`
 * when it does not — the second is the only one staging exercises today
 * (no live run there), so a card tested against only the first would pass
 * green while the real decide button stayed dead in production. Both are
 * exercised here, unedited, exactly as `decisionFor` already composes them.
 */

const RISK = { class: 'low', score: 3, scale: 5 } as const;

function baseProps(overrides: Partial<DecisionCardProps> = {}): DecisionCardProps {
  return {
    approvalId: 'apr-1',
    state: 'pending',
    title: 'Start the guest lxc/122 on pve01',
    requester: 'alert-router',
    originHref: '/runs/run-5',
    originLabel: 'RedisExporterDown',
    category: 'remediation',
    risk: RISK,
    steps: [
      { ordinal: 1, summary: 'Start the guest via Proxmox', capability: 'proxmox_start_guest' },
    ],
    rollback: [
      {
        ordinal: 1,
        summary: 'Ask the guest to shut down and wait',
        capability: 'proxmox_shutdown_guest',
      },
    ],
    reversible: true,
    why: 'The Redis probes fail because the container was shut down.',
    evidence: [
      { summary: '11 entries in the Alertmanager timeline', href: '/incidents/res-1' },
      {
        summary: 'HAL9000 quorate — restarting does not risk the cluster',
        href: '/resources/HAL9000',
      },
    ],
    blastRadiusText: '1 guest · no known dependent service · no HA',
    autonomyText: 'Reversible write — queued, applies only after your yes.',
    rawPayload: JSON.stringify({ capability: 'proxmox_start_guest' }),
    rawPayloadLabel: 'raw action payload',
    ...overrides,
  };
}

function section(container: HTMLElement, name: string): HTMLElement {
  const found = container.querySelector(
    `[data-testid="decision-section"][data-section="${name}"]`,
  );
  if (found === null) {
    throw new Error(`section "${name}" is missing from the card`);
  }
  return found as HTMLElement;
}

describe('a pending, unexpired decision', () => {
  it('renders all six named sections', () => {
    render(<DecisionCard {...baseProps()} />);

    const card = screen.getByTestId('decision-card');
    for (const name of ['steps', 'rollback', 'why', 'evidence', 'blast-radius', 'autonomy']) {
      expect(section(card, name)).toBeTruthy();
    }
  });

  it('numbers steps and rollback steps starting at one', () => {
    render(<DecisionCard {...baseProps()} />);

    const steps = screen.getAllByTestId('decision-step');
    expect(steps).toHaveLength(1);
    expect(within(steps[0]!).getByTestId('step-ordinal')).toHaveTextContent('1');

    const rollback = screen.getAllByTestId('rollback-step');
    expect(rollback).toHaveLength(1);
  });

  it('never renders a JSON fragment outside the closed raw-payload details', () => {
    const { container } = render(<DecisionCard {...baseProps()} />);

    const details = screen.getByTestId('raw-payload');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    const withoutDetails = container.cloneNode(true) as HTMLElement;
    withoutDetails.querySelector('[data-testid="raw-payload"]')?.remove();
    expect(withoutDetails.textContent ?? '').not.toContain('{"');
  });

  it('composes DecisionControls, unedited, when an open interaction is given', () => {
    const labels = {
      approve: 'Approve',
      reject: 'Reject',
      reason: 'Why',
      reasonRequired: 'A reason is required.',
    };
    render(
      <DecisionCard
        {...baseProps()}
        decision={<DecisionControls interactionId="int-1" labels={labels} />}
      />,
    );

    expect(screen.getByTestId('decision')).toBeInTheDocument();
    expect(screen.queryByTestId('proposed-action-decision')).not.toBeInTheDocument();
  });

  it('composes IncidentDecisionControls, unedited, when there is no open interaction', () => {
    const labels = {
      approve: 'Approve',
      reject: 'Reject',
      reason: 'Why',
      reasonRequired: 'A reason is required.',
      failed: 'The deployment did not answer.',
    };
    render(
      <DecisionCard
        {...baseProps()}
        decision={<IncidentDecisionControls approvalId="apr-1" labels={labels} />}
      />,
    );

    expect(screen.getByTestId('proposed-action-decision')).toBeInTheDocument();
    expect(screen.queryByTestId('decision')).not.toBeInTheDocument();
  });

  it('renders no decision control at all for a viewer who may not decide', () => {
    render(<DecisionCard {...baseProps()} decision={undefined} />);

    expect(screen.queryByTestId('decision')).not.toBeInTheDocument();
    expect(screen.queryByTestId('proposed-action-decision')).not.toBeInTheDocument();
    expect(screen.queryByTestId('approve')).not.toBeInTheDocument();
  });
});

describe('an expired decision', () => {
  it('renders the expired footer with both controls and never Approve', () => {
    render(
      <DecisionCard
        {...baseProps({ state: 'expired' })}
        expiredFooter={{
          approvalId: 'apr-1',
          labels: {
            explanation: 'The window closed an hour ago.',
            repropose: 'Propose again, now',
            discard: 'Discard',
            failed: 'The deployment did not answer.',
          },
        }}
      />,
    );

    const footer = screen.getByTestId('expired-footer');
    expect(within(footer).getByTestId('repropose')).toBeInTheDocument();
    expect(within(footer).getByTestId('discard')).toBeInTheDocument();
    expect(screen.queryByTestId('approve')).not.toBeInTheDocument();
    expect(screen.queryByTestId('decision-control')).not.toBeInTheDocument();
  });
});

describe('a decided decision', () => {
  it('renders the outcome rather than any decision control', () => {
    render(
      <DecisionCard
        {...baseProps({ state: 'approved' })}
        outcome={{
          verdict: 'approved',
          decidedBy: 'ana',
          relativeTime: 'yesterday',
          appliedAndVerified: true,
        }}
      />,
    );

    expect(screen.getByTestId('decision-outcome')).toBeInTheDocument();
    expect(screen.queryByTestId('approve')).not.toBeInTheDocument();
    expect(screen.queryByTestId('repropose')).not.toBeInTheDocument();
  });
});

describe('a field the document never named', () => {
  it('renders a declared absence rather than an empty section', () => {
    render(<DecisionCard {...baseProps({ steps: [], why: '', evidence: [] })} />);

    const card = screen.getByTestId('decision-card');
    expect(section(card, 'steps')).toHaveTextContent(/not recorded|no steps/i);
  });

  it('shows the summary as a single labelled step when steps is empty but a summary exists', () => {
    render(
      <DecisionCard
        {...baseProps({
          steps: [],
          summaryFallback: 'Grow the volume that is at the ceiling of its own allocation.',
        })}
      />,
    );

    const steps = screen.getAllByTestId('decision-step');
    expect(steps).toHaveLength(1);
    expect(steps[0]).toHaveTextContent(
      'Grow the volume that is at the ceiling of its own allocation.',
    );
  });

  it('marks the rollback section in danger vocabulary when the action is irreversible', () => {
    render(<DecisionCard {...baseProps({ rollback: [], reversible: false })} />);

    const card = screen.getByTestId('decision-card');
    expect(section(card, 'rollback').getAttribute('data-danger')).toBe('true');
  });
});

describe('the risk gauge', () => {
  it('fills exactly the served score, out of the served scale', () => {
    render(<DecisionCard {...baseProps({ risk: { class: 'high', score: 4, scale: 5 } })} />);

    const gauge = screen.getByTestId('decision-risk');
    expect(gauge).toHaveAttribute('data-risk-score', '4');
    expect(gauge).toHaveAttribute('data-risk-scale', '5');
    const segments = within(gauge).getAllByTestId('risk-segment');
    expect(segments).toHaveLength(5);
    expect(segments.filter((segment) => segment.getAttribute('data-filled') === 'true')).toHaveLength(
      4,
    );
  });
});
