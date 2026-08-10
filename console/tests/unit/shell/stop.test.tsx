import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { KillSwitchBanner, KillSwitchControl } from '@/shell/stop';
import type { Viewer } from '@/session/viewer';

/**
 * The emergency stop, and the asymmetry that makes it useful.
 *
 * Engaging it stops the deployment, so it belongs to whoever may act on the
 * estate. *Knowing* it is engaged belongs to everybody: a screen where nothing
 * is happening looks identical whether nothing needed doing or every automated
 * write is stopped, and an operator who cannot tell those apart goes and does
 * the work by hand — or, worse, engages a second stop.
 *
 * The confirmation names what stops rather than asking whether somebody is
 * sure. "Are you sure" is a question nobody has ever answered no to.
 */

let sent: { url: string; method: string }[] = [];

function answerWith(body: unknown, status = 200): void {
  vi.stubGlobal('fetch', (url: unknown, init: RequestInit) => {
    sent.push({ url: String(url), method: String(init.method) });
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
  answerWith({ ok: true, reachable: true, engaged: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function viewer(permissions: readonly string[]): Viewer {
  return {
    principalId: 'user-under-test',
    displayName: 'Avery Lockhart',
    email: null,
    roles: [],
    permissions: [...permissions],
    teamNodeId: 'team-platform',
    impersonating: false,
    impersonatedBy: null,
  };
}

describe('the banner every viewer sees', () => {
  it('is absent while automation is running, rather than cheerfully present', () => {
    const { container } = render(<KillSwitchBanner locale="en" engaged={false} />);

    expect(container.firstChild).toBeNull();
  });

  it('says what is stopped and what is not, for a viewer holding nothing', () => {
    render(<KillSwitchBanner locale="en" engaged />);

    const banner = screen.getByTestId('stop-banner');
    expect(banner).toHaveTextContent('stopped');
    // The half that stops an operator concluding the deployment is down.
    expect(banner).toHaveTextContent('still run');
  });
});

describe('the control, for whoever may use it', () => {
  it('is not in the document at all for a viewer who may not stop anything', () => {
    const { container } = render(
      <KillSwitchControl
        viewer={viewer(['investigation.read'])}
        locale="en"
        engaged={false}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('names the consequence before it stops anything', async () => {
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged={false}
      />,
    );

    await userEvent.click(screen.getByTestId('engage-stop'));

    expect(screen.getByTestId('stop-confirm')).toHaveTextContent(
      'every automated write, immediately',
    );
    expect(sent).toHaveLength(0);
  });

  it('stops nothing when the confirmation is dismissed', async () => {
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged={false}
      />,
    );

    await userEvent.click(screen.getByTestId('engage-stop'));
    await userEvent.click(screen.getByTestId('cancel-stop'));

    expect(screen.queryByTestId('stop-confirm')).toBeNull();
    expect(sent).toHaveLength(0);
  });

  it('engages through the console’s own courier, and then offers the release', async () => {
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged={false}
      />,
    );

    await userEvent.click(screen.getByTestId('engage-stop'));
    await userEvent.click(screen.getByTestId('confirm-stop'));

    expect(sent.at(-1)).toEqual({ url: '/api/kill-switch', method: 'POST' });
    expect(await screen.findByTestId('release-stop')).toBeInTheDocument();
  });

  it('releases without a confirmation, because letting work happen is not the risk', async () => {
    answerWith({ ok: true, reachable: true, engaged: false });
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged
      />,
    );

    await userEvent.click(screen.getByTestId('release-stop'));

    expect(sent.at(-1)).toEqual({ url: '/api/kill-switch', method: 'DELETE' });
    expect(await screen.findByTestId('engage-stop')).toBeInTheDocument();
  });

  it('says the deployment could not be reached, which sends somebody to the right machine', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged={false}
      />,
    );

    await userEvent.click(screen.getByTestId('engage-stop'));
    await userEvent.click(screen.getByTestId('confirm-stop'));

    expect(await screen.findByTestId('stop-failure')).toHaveTextContent(
      'could not be reached',
    );
  });
});
