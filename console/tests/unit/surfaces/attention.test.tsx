import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AttentionBlock, type DecisionCardData } from '@/surfaces/attention';

/**
 * "Precisa de você": the plan is visible before either button is, the
 * oldest pending decision is expanded, the rest are compact with a count,
 * and an empty queue says so with a link to the history.
 */

function decision(over: Partial<DecisionCardData> = {}): DecisionCardData {
  return {
    id: 'apr-1',
    title: 'Reboot the guest lxc/122 on pve01',
    riskClass: 'moderate',
    since: '1h ago',
    steps: [{ ordinal: 1, summary: 'Reboot the guest' }],
    rollback: [{ ordinal: 1, summary: 'No rollback needed: rebooting is idempotent' }],
    ...over,
  };
}

describe('AttentionBlock', () => {
  it('is a named empty state with a link to the decision history, not a blank band', () => {
    render(<AttentionBlock locale="en" decisions={[]} canDecide />);

    const empty = screen.getByTestId('attention-decision-empty');
    expect(empty).toBeInTheDocument();
    expect(empty.querySelector('a')).toHaveAttribute('href', '/decisions');
  });

  it('shows the plan and the reversal on the one pending card, expanded', () => {
    render(<AttentionBlock locale="en" decisions={[decision()]} canDecide />);

    const card = screen.getByTestId('attention-decision-card');
    expect(card).toHaveAttribute('data-expanded', 'true');
    expect(screen.getByTestId('attention-decision-plan')).toHaveTextContent('Reboot the guest');
    expect(screen.getByTestId('attention-decision-rollback')).toHaveTextContent(
      'No rollback needed',
    );
  });

  it('expands only the oldest of several pending decisions, and counts the rest', () => {
    render(
      <AttentionBlock
        locale="en"
        decisions={[
          decision({ id: 'apr-1' }),
          decision({ id: 'apr-2' }),
          decision({ id: 'apr-3' }),
        ]}
        canDecide
      />,
    );

    const cards = screen.getAllByTestId('attention-decision-card');
    expect(cards).toHaveLength(3);
    expect(cards[0]).toHaveAttribute('data-expanded', 'true');
    expect(cards[1]).toHaveAttribute('data-expanded', 'false');
    expect(cards[2]).toHaveAttribute('data-expanded', 'false');
    expect(screen.getByText('2 more waiting →')).toBeInTheDocument();
  });

  it('is informative rather than interactive without the permission to decide', () => {
    render(<AttentionBlock locale="en" decisions={[decision()]} canDecide={false} />);

    expect(screen.getByTestId('attention-decision-no-permission')).toBeInTheDocument();
    expect(screen.queryByTestId('decision-control')).toBeNull();
  });

  it('always reaches the full decision in one click, whichever card it is', () => {
    render(
      <AttentionBlock
        locale="en"
        decisions={[decision({ id: 'apr-1' }), decision({ id: 'apr-2' })]}
        canDecide
      />,
    );

    const links = screen.getAllByTestId('attention-view-plan');
    expect(links[0]).toHaveAttribute('href', '/decisions?tab=actions&selected=apr-1');
    expect(links[1]).toHaveAttribute('href', '/decisions?tab=actions&selected=apr-2');
  });
});
