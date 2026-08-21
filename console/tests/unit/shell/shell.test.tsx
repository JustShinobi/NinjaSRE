import { render, screen, waitFor } from '@testing-library/react';
import { Suspense } from 'react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EN } from '@/i18n/en';
import { sessionController } from '@/session/controller';
import { SESSION_WARNING_SECONDS } from '@/session/cookies';
import { publishResolved, type AttentionItem } from '@/shell/attention';
import { Shell } from '@/shell/shell';

import { owner, viewerAt } from './support';

/**
 * The frame, and the four behaviours that have to be identical on every page.
 *
 * The one worth stating is the first: the chrome renders before any page data
 * exists. `children` here is a component that never resolves, which is what a
 * slow API looks like from inside the shell — and the sidebar, the utility bar
 * and the footer are all present anyway.
 */

const GUARDIAN = { live: true, posture: 'propose' } as const;

const WAITING: readonly AttentionItem[] = [
  {
    id: 'apr-0001',
    kind: 'approval',
    title: 'Reclaim 41 GiB on local-lvm',
    detail: 'awaiting decision',
    href: '/approvals/apr-0001',
    since: '2026-08-07T09:46:00+00:00',
  },
];

function renderShell(overrides: Partial<Parameters<typeof Shell>[0]> = {}): {
  navigate: ReturnType<typeof vi.fn>;
} {
  const navigate = vi.fn();
  render(
    <Shell
      viewer={owner()}
      locale="en"
      deployment={{ name: 'HAL9000', timezone: 'UTC' }}
      current="/"
      guardian={GUARDIAN}
      attention={WAITING}
      recentRuns={[]}
      navigate={navigate}
      {...overrides}
    >
      <p data-testid="page">the page</p>
    </Shell>,
  );
  return { navigate };
}

beforeEach(() => {
  sessionController.reset();
});

afterEach(() => {
  sessionController.reset();
});

describe('the shell renders before the page does', () => {
  it('draws the chrome around a page that never arrives', () => {
    const navigate = vi.fn();
    // A component that suspends for ever is what a stalled API looks like from
    // inside the shell. The boundary is around the *page*, exactly where the
    // router puts one, so the chrome is outside it and cannot be waiting.
    // Thrown rather than returned: suspending is what React does with a thrown
    // promise, and a stalled server component is exactly that from here.
    const pending: unknown = new Promise<never>(() => undefined);
    function NeverResolves(): never {
      throw pending;
    }

    render(
      <Shell
        viewer={owner()}
        locale="en"
        deployment={{ name: 'HAL9000', timezone: 'UTC' }}
        current="/"
        guardian={GUARDIAN}
        attention={[]}
        recentRuns={[]}
        navigate={navigate}
      >
        <Suspense fallback={<p data-testid="page-pending" />}>
          <NeverResolves />
        </Suspense>
      </Shell>,
    );

    expect(screen.getByTestId('page-pending')).toBeInTheDocument();
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('topbar')).toBeInTheDocument();
    expect(screen.getByTestId('guardian')).toBeInTheDocument();
    expect(screen.getByTestId('deployment-name')).toHaveTextContent('HAL9000');
  });

  it('puts the page inside the main landmark, once there is one', () => {
    renderShell();
    expect(screen.getByTestId('main')).toContainElement(screen.getByTestId('page'));
  });
});

describe('the palette, from anywhere', () => {
  it('opens on the shortcut, wherever the focus is', async () => {
    renderShell();
    expect(screen.queryByTestId('palette')).toBeNull();

    await userEvent.keyboard('{Control>}k{/Control}');

    expect(screen.getByTestId('palette')).toBeInTheDocument();
  });

  it('closes without changing the page', async () => {
    const { navigate } = renderShell();
    await userEvent.keyboard('{Control>}k{/Control}');
    await userEvent.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByTestId('palette')).toBeNull();
    });
    expect(navigate).not.toHaveBeenCalled();
  });

  it('forgets the last search when it is opened again', async () => {
    renderShell();
    await userEvent.keyboard('{Control>}k{/Control}');
    await userEvent.keyboard('audit');
    await userEvent.keyboard('{Escape}');
    await userEvent.keyboard('{Control>}k{/Control}');

    expect(screen.getByTestId('palette-query')).toHaveValue('');
  });

  it('navigates when a command is run, and closes behind itself', async () => {
    const { navigate } = renderShell();
    await userEvent.keyboard('{Control>}k{/Control}');
    await userEvent.keyboard('audit{Enter}');

    expect(navigate).toHaveBeenCalledWith('/audit');
    await waitFor(() => {
      expect(screen.queryByTestId('palette')).toBeNull();
    });
  });
});

describe('the drawer, below the breakpoint', () => {
  it('carries the same navigation and loses nothing', async () => {
    renderShell();
    const inTheRail = screen
      .getAllByTestId('nav-entry')
      .map((entry) => entry.getAttribute('data-area'));

    await userEvent.click(screen.getByTestId('open-drawer'));

    const everywhere = screen
      .getAllByTestId('nav-entry')
      .map((entry) => entry.getAttribute('data-area'));
    // Every entry twice: once in the rail, once in the drawer. Nothing is lost.
    for (const area of inTheRail) {
      expect(everywhere.filter((each) => each === area)).toHaveLength(2);
    }
    expect(screen.getAllByTestId('guardian')).toHaveLength(2);
  });

  it('closes when a viewer navigates from inside it', async () => {
    renderShell();
    await userEvent.click(screen.getByTestId('open-drawer'));
    const inDrawer = screen.getAllByTestId('nav-entry').at(-1);
    expect(inDrawer).toBeDefined();
    if (inDrawer === undefined) return;

    await userEvent.click(inDrawer);

    await waitFor(() => {
      expect(screen.getAllByTestId('guardian')).toHaveLength(1);
    });
  });
});

describe('the notification centre, inside the shell', () => {
  it('opens from the utility bar and shows what is waiting', async () => {
    renderShell();
    await userEvent.click(screen.getByTestId('open-notifications'));

    expect(screen.getByTestId('notifications')).toBeInTheDocument();
    expect(screen.getAllByTestId('notification')).toHaveLength(1);
  });

  it('clears an item resolved anywhere else, with no refresh', async () => {
    renderShell();
    await userEvent.click(screen.getByTestId('open-notifications'));
    expect(screen.getByTestId('unread-count')).toHaveTextContent('1');

    // Published by whatever surface granted the approval. The shell hears it.
    publishResolved('apr-0001');

    await waitFor(() => {
      expect(screen.queryByTestId('unread-count')).toBeNull();
    });
    expect(screen.getByTestId('notifications-empty')).toBeInTheDocument();
  });

  it('ignores a resolution for something it is not showing', async () => {
    renderShell();
    publishResolved('apr-9999');

    await userEvent.click(screen.getByTestId('open-notifications'));
    expect(screen.getAllByTestId('notification')).toHaveLength(1);
  });
});

describe('the session, from inside the shell', () => {
  it('sends the viewer to the sign-in once, however many calls were refused', async () => {
    const { navigate } = renderShell({ current: '/approvals' });

    sessionController.unauthorized('/approvals');
    sessionController.unauthorized('/approvals');
    sessionController.unauthorized('/approvals');

    await waitFor(() => {
      expect(navigate).toHaveBeenCalledTimes(1);
    });
    expect(navigate.mock.calls[0]?.[0]).toContain('from=%2Fapprovals');
    expect(navigate.mock.calls[0]?.[0]).toContain('reason=expired');
  });

  it('ends the session on the server before it leaves', async () => {
    const ending = vi.fn(() => Promise.resolve(new Response('{}', { status: 200 })));
    vi.stubGlobal('fetch', ending);
    const { navigate } = renderShell({ current: '/knowledge' });

    await userEvent.click(screen.getByTestId('sign-out'));

    await waitFor(() => {
      expect(navigate).toHaveBeenCalledOnce();
    });
    // Navigating away with the cookie still set is not signing out; it is
    // closing a tab, and the next person at that keyboard is still signed in.
    const [address, init] = ending.mock.calls[0] as unknown as [string, RequestInit];
    expect(address).toBe('/api/session');
    expect(init.method).toBe('DELETE');
    expect(navigate.mock.calls[0]?.[0]).toContain('reason=signed-out');
    vi.unstubAllGlobals();
  });

  it('still leaves when the sign-out request itself fails', async () => {
    // The viewer has decided to go. Refusing to take them to the sign-in
    // because a request failed leaves them inside a console they abandoned.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('network'))),
    );
    const { navigate } = renderShell({ current: '/knowledge' });

    await userEvent.click(screen.getByTestId('sign-out'));

    await waitFor(() => {
      expect(navigate).toHaveBeenCalledOnce();
    });
    vi.unstubAllGlobals();
  });

  it('warns before the session ends rather than after', () => {
    const ending = new Date(Date.now() + (SESSION_WARNING_SECONDS - 30) * 1000);
    renderShell({ expiresAt: ending.toISOString() });

    expect(screen.getByTestId('session-expiring')).toBeInTheDocument();
    expect(screen.getByTestId('stay-signed-in')).toBeInTheDocument();
  });

  it('says nothing while the session has plenty of time left', () => {
    const ending = new Date(Date.now() + (SESSION_WARNING_SECONDS + 600) * 1000);
    renderShell({ expiresAt: ending.toISOString() });

    expect(screen.queryByTestId('session-expiring')).toBeNull();
  });

  it('says nothing when it was never told when the session ends', () => {
    renderShell({ expiresAt: null });
    expect(screen.queryByTestId('session-expiring')).toBeNull();
  });
});

describe('impersonation, above every page', () => {
  it('is rendered by the shell rather than by a page, so no page can forget', () => {
    renderShell({
      viewer: viewerAt('viewer', {
        displayName: 'Reese Underhill',
        impersonating: true,
        impersonatedBy: 'Avery Lockhart',
      }),
    });

    const banner = screen.getByTestId('impersonation');
    expect(banner.textContent).toContain('Reese Underhill');
    expect(banner.textContent).toContain('Avery Lockhart');
    expect(banner.compareDocumentPosition(screen.getByTestId('main'))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
});

describe('what the shell renders in Portuguese', () => {
  it('takes the chrome from the catalogue rather than from the source language', () => {
    renderShell({ locale: 'pt-BR' });
    expect(screen.queryByText(EN['nav.audit'])).toBeNull();
  });
});
