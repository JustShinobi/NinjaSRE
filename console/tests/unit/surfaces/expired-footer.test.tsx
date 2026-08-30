import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ExpiredFooterControls } from '@/surfaces/expired-footer';

/**
 * The expired card's one exit, against the backend's own refusal — not a
 * stack trace, and not a generic sentence when the deployment named a real
 * cause (an origin gone, a pending already reproposed).
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const LABELS = {
  explanation: 'The window for answering this closed.',
  repropose: 'Propose again, now',
  discard: 'Discard',
  failed: 'The deployment did not answer. Nothing changed.',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the expired footer, refused', () => {
  it('shows the backend refusal by name on a named 422', async () => {
    stubFetchResponse(422, { detail: "'apr-9' cannot be rebuilt" });
    render(<ExpiredFooterControls approvalId="apr-9" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('repropose'));

    expect(await screen.findByTestId('expired-footer-failed')).toHaveTextContent(
      "'apr-9' cannot be rebuilt",
    );
  });

  it('falls back to the generic sentence when the deployment never answered', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new Error('network down')));
    render(<ExpiredFooterControls approvalId="apr-9" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('discard'));

    expect(await screen.findByTestId('expired-footer-failed')).toHaveTextContent(LABELS.failed);
  });

  it('falls back to the generic sentence when a failure body carries no cause', async () => {
    stubFetchResponse(500, {});
    render(<ExpiredFooterControls approvalId="apr-9" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('repropose'));

    expect(await screen.findByTestId('expired-footer-failed')).toHaveTextContent(LABELS.failed);
  });
});

function stubFetchResponse(status: number, body: Record<string, unknown>): void {
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  );
}
