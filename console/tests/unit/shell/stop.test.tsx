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

describe('who stopped it, since when, and how it comes back', () => {
  it('says nothing about who or when when the deployment did not say', () => {
    render(<KillSwitchBanner locale="en" engaged />);

    const banner = screen.getByTestId('stop-banner');
    expect(banner).toHaveTextContent('before this page could say who or when');
    // Always says how it comes back, whether or not it knows who stopped it.
    expect(banner).toHaveTextContent('release it from the top of the screen');
  });

  it('names who stopped it and since when, in the deployment’s own zone', () => {
    render(
      <KillSwitchBanner
        locale="en"
        engaged
        by="Avery Lockhart"
        since="2026-08-07T09:00:00Z"
        zone="UTC"
      />,
    );

    const banner = screen.getByTestId('stop-banner');
    expect(banner).toHaveTextContent('Stopped by Avery Lockhart');
  });

  it('attributes an engagement it just performed to whoever the deployment says', async () => {
    // The courier forwards `scopes` alongside `engaged`, so the browser reads
    // the deployment's answer rather than asserting its own. Named someone
    // other than the acting viewer on purpose: attributing to `viewer` would
    // pass either way, and this is the assertion that tells the two apart.
    answerWith({
      ok: true,
      reachable: true,
      engaged: true,
      scopes: {
        '*': { engaged_by: 'Reese Underhill', engaged_at: '2026-08-07T09:00:00Z' },
      },
    });
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        zone="UTC"
        engaged={false}
      />,
    );

    await userEvent.click(screen.getByTestId('engage-stop'));
    await userEvent.click(screen.getByTestId('confirm-stop'));

    expect(await screen.findByTestId('release-stop')).toBeInTheDocument();
    expect(screen.getByTestId('stop-attribution')).toHaveTextContent(
      'Stopped by Reese Underhill',
    );
  });

  it('invents no attribution when the deployment engaged the stop without saying who', async () => {
    answerWith({ ok: true, reachable: true, engaged: true, scopes: {} });
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged={false}
      />,
    );

    await userEvent.click(screen.getByTestId('engage-stop'));
    await userEvent.click(screen.getByTestId('confirm-stop'));

    expect(await screen.findByTestId('release-stop')).toBeInTheDocument();
    // The estate is stopped and the console says so; who did it is a fact
    // nobody gave it, and the viewer holding the button is not an answer.
    expect(screen.queryByTestId('stop-attribution')).toBeNull();
  });

  it('carries who and when the frame already knew, from its first render', () => {
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged
        by="Reese Underhill"
        since="2026-08-07T09:00:00Z"
        zone="UTC"
      />,
    );

    expect(screen.getByTestId('stop-attribution')).toHaveTextContent(
      'Stopped by Reese Underhill',
    );
  });

  it('drops the attribution once it is released', async () => {
    answerWith({ ok: true, reachable: true, engaged: false });
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged
        by="Reese Underhill"
        since="2026-08-07T09:00:00Z"
        zone="UTC"
      />,
    );

    await userEvent.click(screen.getByTestId('release-stop'));

    expect(await screen.findByTestId('engage-stop')).toBeInTheDocument();
    expect(screen.queryByTestId('stop-attribution')).toBeNull();
  });
});

describe('when the deployment refuses', () => {
  it('says it refused rather than reporting a stop that did not happen', async () => {
    answerWith({ ok: false, reachable: true }, 403);
    render(
      <KillSwitchControl
        viewer={viewer(['remediation.execute'])}
        locale="en"
        engaged={false}
      />,
    );

    await userEvent.click(screen.getByTestId('engage-stop'));
    await userEvent.click(screen.getByTestId('confirm-stop'));

    expect(await screen.findByTestId('stop-failure')).toBeInTheDocument();
    expect(screen.queryByTestId('release-stop')).toBeNull();
  });
});
