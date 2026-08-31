import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AttentionBlock, type DecisionCardData } from '@/surfaces/attention';

/**
 * "Precisa de você": the plan is visible before either button is, the
 * oldest pending decision is expanded, the rest are compact with a count,
 * and an empty queue says so with a link to the history.
 */

const REFRESH = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: REFRESH }),
}));

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
    expect(screen.getByTestId('attention-decision-plan')).toHaveTextContent(
      'Reboot the guest',
    );
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
    expect(screen.queryByTestId('attention-approve')).toBeNull();
    expect(screen.queryByTestId('attention-reject')).toBeNull();
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

describe('AttentionBlock, deciding inline', () => {
  beforeEach(() => {
    REFRESH.mockClear();
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function sentBody(): Record<string, unknown> {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const [, init] = fetchMock.mock.calls[0] as [string, { body: string }];
    return JSON.parse(init.body) as Record<string, unknown>;
  }

  it('shows the approve control enabled before any click, beside the plan already visible', () => {
    render(
      <AttentionBlock locale="en" decisions={[decision({ id: 'apr-1' })]} canDecide />,
    );

    expect(screen.getByTestId('attention-decision-plan')).toBeVisible();
    expect(screen.getByTestId('attention-decision-rollback')).toBeVisible();
    expect(screen.getByTestId('attention-approve')).toBeEnabled();
  });

  it('approves with no reason, and refreshes once the deployment records it', async () => {
    render(
      <AttentionBlock locale="en" decisions={[decision({ id: 'apr-1' })]} canDecide />,
    );

    fireEvent.click(screen.getByTestId('attention-approve'));
    await vi.waitFor(() => {
      expect(REFRESH).toHaveBeenCalled();
    });
    expect(sentBody().payload).toEqual({ verdict: 'approve', reason: '' });
  });

  it('reveals the reason field only once Recusar is clicked, disables submit until it is filled', () => {
    render(
      <AttentionBlock locale="en" decisions={[decision({ id: 'apr-1' })]} canDecide />,
    );

    expect(screen.queryByTestId('attention-reject-reason')).toBeNull();

    fireEvent.click(screen.getByTestId('attention-reject'));
    const reasonField = screen.getByTestId('attention-reject-reason');
    expect(reasonField).toBeVisible();
    const submit = screen.getByTestId('attention-reject-submit');
    expect(submit).toBeDisabled();

    fireEvent.change(reasonField, { target: { value: 'not a real problem' } });
    expect(submit).toBeEnabled();
  });

  it('sends the rejection and its reason once submitted, and refreshes', async () => {
    render(
      <AttentionBlock locale="en" decisions={[decision({ id: 'apr-1' })]} canDecide />,
    );

    fireEvent.click(screen.getByTestId('attention-reject'));
    fireEvent.change(screen.getByTestId('attention-reject-reason'), {
      target: { value: 'the workload recovered on its own' },
    });
    fireEvent.click(screen.getByTestId('attention-reject-submit'));

    await vi.waitFor(() => {
      expect(REFRESH).toHaveBeenCalled();
    });
    const body = sentBody();
    expect(body.operation).toBe('decide');
    expect(body.target).toBe('apr-1');
    expect(body.payload).toEqual({
      verdict: 'reject',
      reason: 'the workload recovered on its own',
    });
  });

  it('says so, rather than looking decided, when the deployment does not record the decision', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false })),
    );
    render(
      <AttentionBlock locale="en" decisions={[decision({ id: 'apr-1' })]} canDecide />,
    );

    fireEvent.click(screen.getByTestId('attention-approve'));
    await vi.waitFor(() => {
      expect(screen.getByTestId('attention-decision-failed')).toBeInTheDocument();
    });
    expect(REFRESH).not.toHaveBeenCalled();
  });
});
