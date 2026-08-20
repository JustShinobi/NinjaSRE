import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { IncidentDecisionControls } from '@/surfaces/screens/incident-decision-controls';

/**
 * The two controls on a proposed action, exercised by pressing them.
 *
 * The claims worth holding here are about what does *not* happen. A reject
 * with no reason must not reach the deployment at all — not be sent and
 * refused, not be sent and ignored — because a rejection nobody gave a reason
 * for is a decision nobody can reconstruct later. And a decision that failed
 * to record must say so rather than leave the page looking decided, since the
 * operator's next move depends on knowing the deployment did not hear them.
 *
 * Neither control carries the action out. Approving records a decision; the
 * effect is a separate mechanism this component never invokes, which is why
 * these tests assert on the request that goes out rather than on any outcome.
 */

const REFRESH = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: REFRESH }),
}));

const LABELS = {
  approve: 'Approve and run',
  reject: 'Reject',
  reason: 'Reason',
  reasonRequired: 'A reason is required to reject.',
  failed: 'The decision was not recorded. Try again.',
};

function controls(): void {
  render(<IncidentDecisionControls approvalId="apr-1" labels={LABELS} />);
}

/** Return the JSON body of the one request that was sent. */
function sentBody(): Record<string, unknown> {
  const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const [, init] = fetchMock.mock.calls[0] as [string, { body: string }];
  return JSON.parse(init.body) as Record<string, unknown>;
}

function answerWith(ok: boolean): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok })),
  );
}

beforeEach(() => {
  REFRESH.mockClear();
  answerWith(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('rejecting without a reason', () => {
  it('never reaches the deployment, and says why not', () => {
    controls();

    expect(screen.getByText(LABELS.reasonRequired)).toBeInTheDocument();

    const reject = screen.getByRole('button', { name: LABELS.reject });
    expect(reject).toBeDisabled();

    fireEvent.click(reject);

    // The claim is the absence of a request, not the presence of a refusal.
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(REFRESH).not.toHaveBeenCalled();
  });
});

describe('deciding', () => {
  it('sends the rejection and its reason once a reason is given', async () => {
    controls();

    fireEvent.change(screen.getByLabelText(LABELS.reason), {
      target: { value: 'the workload recovered on its own' },
    });

    const reject = screen.getByRole('button', { name: LABELS.reject });
    expect(reject).toBeEnabled();
    expect(screen.queryByText(LABELS.reasonRequired)).not.toBeInTheDocument();

    fireEvent.click(reject);
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

  it('sends the approval, and needs no reason for it', async () => {
    controls();

    fireEvent.click(screen.getByRole('button', { name: LABELS.approve }));
    await vi.waitFor(() => {
      expect(REFRESH).toHaveBeenCalled();
    });

    expect(sentBody().payload).toEqual({ verdict: 'approve', reason: '' });
  });
});

describe('when the deployment does not record the decision', () => {
  it('says so rather than leaving the page looking decided', async () => {
    answerWith(false);
    controls();

    fireEvent.click(screen.getByRole('button', { name: LABELS.approve }));
    await vi.waitFor(() => {
      expect(screen.getByTestId('decision-failed')).toBeInTheDocument();
    });

    expect(screen.getByTestId('decision-failed')).toHaveTextContent(LABELS.failed);
    // Not refreshed: the page must not redraw as though a decision landed.
    expect(REFRESH).not.toHaveBeenCalled();
  });

  it('says the same thing when the request never arrives at all', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('the network is gone'))),
    );
    controls();

    fireEvent.click(screen.getByRole('button', { name: LABELS.approve }));
    await vi.waitFor(() => {
      expect(screen.getByTestId('decision-failed')).toBeInTheDocument();
    });

    expect(REFRESH).not.toHaveBeenCalled();
  });
});
