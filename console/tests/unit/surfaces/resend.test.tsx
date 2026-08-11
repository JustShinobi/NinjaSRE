import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RESEND_ENDPOINT, Resend } from '@/surfaces/resend';

/**
 * A report that did not arrive, and the control that sends it again.
 *
 * The control says what happened rather than disappearing, including when the
 * second attempt failed too — an operator who re-sent something and saw nothing
 * change has no way to tell a delivered message from a button that did nothing.
 */

const LABELS = {
  resend: 'Send again',
  resending: 'Sending…',
  delivered: 'Delivered',
  failed: 'It did not arrive this time either.',
  unreachable: 'The deployment could not be reached.',
};

type Fetch = (input: string, init: RequestInit) => Promise<Response>;

function answered(body: unknown, status = 200): ReturnType<typeof vi.fn<Fetch>> {
  const calls = vi.fn<Fetch>(() =>
    Promise.resolve(new Response(JSON.stringify(body), { status })),
  );
  vi.stubGlobal('fetch', calls);
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('sending a failed delivery again', () => {
  it('asks the deployment, naming the delivery', async () => {
    const calls = answered({ outcome: 'delivered' });
    render(<Resend deliveryId="ops:concluded:1" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('resend-action'));

    expect(calls).toHaveBeenCalledWith(RESEND_ENDPOINT, expect.anything());
    const sent = calls.mock.calls[0]?.[1].body;
    expect(typeof sent === 'string' ? sent : '').toContain('ops:concluded:1');
  });

  it('says it arrived when it did', async () => {
    answered({ outcome: 'delivered' });
    render(<Resend deliveryId="ops:concluded:1" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('resend-action'));

    expect(screen.getByTestId('resend-outcome')).toHaveTextContent(LABELS.delivered);
  });

  it('says it did not arrive this time either, rather than nothing', async () => {
    answered({ outcome: 'failed' });
    render(<Resend deliveryId="ops:concluded:1" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('resend-action'));

    expect(screen.getByTestId('resend-outcome')).toHaveTextContent(LABELS.failed);
  });

  it('says so when the deployment refuses the re-send', async () => {
    answered({}, 400);
    render(<Resend deliveryId="ops:concluded:1" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('resend-action'));

    expect(screen.getByTestId('resend-outcome')).toHaveTextContent(LABELS.failed);
  });

  it('says so when the deployment cannot be reached', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('no route'))),
    );
    render(<Resend deliveryId="ops:concluded:1" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('resend-action'));

    expect(screen.getByTestId('resend-outcome')).toHaveTextContent(LABELS.unreachable);
  });
});
