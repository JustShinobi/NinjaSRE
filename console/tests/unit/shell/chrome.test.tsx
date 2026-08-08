import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SHELL, SIDEBAR_BREAKPOINT } from '@/design/tokens';
import { EN } from '@/i18n/en';
import { message } from '@/i18n/messages';
import { ImpersonationBanner } from '@/shell/impersonation';
import { NotificationCentre } from '@/shell/notifications';
import { AREAS, NAV_GROUPS } from '@/shell/routes';
import { Sidebar } from '@/shell/sidebar';
import { Topbar } from '@/shell/topbar';
import type { AttentionItem } from '@/shell/attention';

import { owner, viewerAt } from './support';

/**
 * The chrome, against the design it was drawn from.
 *
 * Four of these assertions are the design-fidelity claims the feature is judged
 * on — the four groups in order, the sidebar's width, the utility bar's height,
 * and the sidebar footer stating guardian liveness and posture on every page.
 * They are here rather than only in a screenshot because a screenshot can only
 * show a difference to somebody who looks at it.
 */

const GUARDIAN = { live: true, posture: 'propose' } as const;

function nothing(): void {
  // The chrome's handlers are not what this file is about.
}

function renderSidebar(current = '/'): void {
  render(
    <Sidebar viewer={owner()} locale="en" current={current} guardian={GUARDIAN} />,
  );
}

describe('the sidebar', () => {
  it('draws the four groups the design draws, in the documented order', () => {
    renderSidebar();
    const headings = screen
      .getAllByText(
        new RegExp(
          `^(${NAV_GROUPS.map((group) => message('en', `nav.group.${group}`)).join('|')})$`,
        ),
      )
      .map((element) => element.textContent);

    expect(headings).toEqual(
      NAV_GROUPS.map((group) => message('en', `nav.group.${group}`)),
    );
  });

  it('is as wide as the design draws it', () => {
    renderSidebar();
    // The number lives in the token table and the utility reads it, so this
    // asserts the sidebar names the token rather than what the token holds.
    expect(screen.getByTestId('sidebar').className).toContain('w-sidebar');
    expect(SHELL.sidebar).toBe(236);
  });

  it('gives every entry an icon as well as a label', () => {
    renderSidebar();
    for (const entry of screen.getAllByTestId('nav-entry')) {
      const area = entry.getAttribute('data-area') ?? 'an unnamed entry';
      expect(entry.querySelector('svg'), area).not.toBeNull();
      expect(entry.textContent.trim(), area).not.toBe('');
    }
  });

  it('marks exactly one entry as current, and marks the right one', () => {
    renderSidebar('/audit');
    const marked = screen
      .getAllByTestId('nav-entry')
      .filter((entry) => entry.getAttribute('aria-current') === 'page');

    expect(marked).toHaveLength(1);
    expect(marked[0]?.getAttribute('data-area')).toBe('audit');
  });

  it('marks the area a nested route belongs to, not nothing at all', () => {
    renderSidebar('/runs/run-0001');
    const marked = screen
      .getAllByTestId('nav-entry')
      .filter((entry) => entry.getAttribute('aria-current') === 'page');

    expect(marked[0]?.getAttribute('data-area')).toBe('runs');
  });

  it('does not mark the overview current on every other page', () => {
    // `/` is a prefix of everything, so the obvious implementation marks the
    // overview on all twelve routes.
    renderSidebar('/knowledge');
    const marked = screen
      .getAllByTestId('nav-entry')
      .filter((entry) => entry.getAttribute('aria-current') === 'page');

    expect(marked[0]?.getAttribute('data-area')).toBe('knowledge');
  });

  it('collapses below the documented breakpoint rather than narrowing', () => {
    renderSidebar();
    // Tailwind's `md` is the breakpoint the design declares. A sidebar squeezed
    // onto a phone is a column of wrapped words costing a third of the screen.
    expect(screen.getByTestId('sidebar').className).toContain('hidden');
    expect(screen.getByTestId('sidebar').className).toContain('md:flex');
    expect(SIDEBAR_BREAKPOINT).toBe(768);
  });

  it('always says whether the guardian is alive and what posture it is in', () => {
    renderSidebar();
    const footer = screen.getByTestId('guardian');

    expect(footer).toHaveAttribute('data-live', 'true');
    expect(footer).toHaveAttribute('data-posture', 'propose');
    expect(footer.textContent).toContain(EN['shell.guardian.active']);
    expect(footer.textContent).toContain(EN['shell.guardian.posture.propose']);
  });

  it('says so when the guardian is not alive, rather than saying nothing', () => {
    render(
      <Sidebar
        viewer={owner()}
        locale="en"
        current="/"
        guardian={{ live: false, posture: 'frozen' }}
      />,
    );

    expect(screen.getByTestId('guardian')).toHaveAttribute('data-live', 'false');
    expect(screen.getByTestId('guardian').textContent).toContain(
      EN['shell.guardian.silent'],
    );
  });

  it('carries a count on the areas that have one waiting', () => {
    render(
      <Sidebar
        viewer={owner()}
        locale="en"
        current="/"
        guardian={GUARDIAN}
        counts={{ approvals: 2, incidents: 3, runs: 0 }}
      />,
    );

    const counts = screen.getAllByTestId('nav-count').map((each) => each.textContent);
    expect(counts).toEqual(['3', '2']);
  });

  it('renders every label from the catalogue, in whichever language the viewer reads', () => {
    render(<Sidebar viewer={owner()} locale="pt-BR" current="/" guardian={GUARDIAN} />);

    expect(screen.getByText(message('pt-BR', 'nav.audit'))).toBeInTheDocument();
    expect(screen.queryByText(EN['nav.audit'])).toBeNull();
  });
});

describe('the utility bar', () => {
  function renderTopbar(attention: readonly AttentionItem[] = []): {
    palette: ReturnType<typeof vi.fn>;
    drawer: ReturnType<typeof vi.fn>;
    notifications: ReturnType<typeof vi.fn>;
  } {
    const palette = vi.fn();
    const drawer = vi.fn();
    const notifications = vi.fn();
    render(
      <Topbar
        viewer={owner()}
        locale="en"
        deployment={{ name: 'HAL9000', timezone: 'UTC' }}
        attention={attention}
        onOpenPalette={palette}
        onOpenNotifications={notifications}
        onOpenDrawer={drawer}
        onSignOut={nothing}
      />,
    );
    return { palette, drawer, notifications };
  }

  it('is as tall as the design draws it', () => {
    renderTopbar();
    expect(screen.getByTestId('topbar').className).toContain('h-topbar');
    expect(SHELL.topbar).toBe(52);
  });

  it('carries the deployment name, the theme switch, the centre and the account', () => {
    renderTopbar();

    expect(screen.getByTestId('deployment-name')).toHaveTextContent('HAL9000');
    expect(screen.getByTestId('theme-switch')).toBeInTheDocument();
    expect(screen.getByTestId('open-notifications')).toBeInTheDocument();
    expect(screen.getByTestId('account')).toBeInTheDocument();
  });

  it('shows no unread count when nothing is waiting', () => {
    renderTopbar();
    expect(screen.queryByTestId('unread-count')).toBeNull();
  });

  it('shows the count when something is', () => {
    renderTopbar([
      {
        id: 'apr-0001',
        kind: 'approval',
        title: 'Reclaim 41 GiB',
        detail: 'awaiting decision',
        href: '/approvals/apr-0001',
        since: '2026-08-07T11:39:00+00:00',
      },
    ]);
    expect(screen.getByTestId('unread-count')).toHaveTextContent('1');
  });

  it('cycles the theme through light, dark and the system', async () => {
    renderTopbar();
    const control = screen.getByTestId('theme-switch');

    expect(control).toHaveAttribute('data-theme-choice', 'system');
    await userEvent.click(control);
    expect(control).toHaveAttribute('data-theme-choice', 'light');
    await userEvent.click(control);
    expect(control).toHaveAttribute('data-theme-choice', 'dark');
    await userEvent.click(control);
    // Back to following the system, which is a choice rather than a third theme.
    expect(control).toHaveAttribute('data-theme-choice', 'system');
  });

  it('opens the palette and the drawer through the controls that say so', async () => {
    const { palette, drawer } = renderTopbar();

    await userEvent.click(screen.getByTestId('open-palette'));
    await userEvent.click(screen.getByTestId('open-drawer'));

    expect(palette).toHaveBeenCalledOnce();
    expect(drawer).toHaveBeenCalledOnce();
  });
});

describe('the impersonation banner', () => {
  it('is absent when nobody is impersonating', () => {
    render(<ImpersonationBanner viewer={owner()} locale="en" />);
    expect(screen.queryByTestId('impersonation')).toBeNull();
  });

  it('names both parties', () => {
    render(
      <ImpersonationBanner
        viewer={viewerAt('viewer', {
          displayName: 'Reese Underhill',
          impersonating: true,
          impersonatedBy: 'Avery Lockhart',
        })}
        locale="en"
      />,
    );

    const banner = screen.getByTestId('impersonation');
    expect(banner.textContent).toContain('Reese Underhill');
    expect(banner.textContent).toContain('Avery Lockhart');
  });

  it('offers no way to dismiss it', () => {
    render(
      <ImpersonationBanner
        viewer={viewerAt('viewer', { impersonating: true, impersonatedBy: 'admin' })}
        locale="en"
      />,
    );

    // A banner that can be dismissed is dismissed once and then absent for the
    // rest of the session, which is the whole of the time it was needed.
    expect(screen.getByTestId('impersonation').querySelector('button')).toBeNull();
  });

  it('renders the same on every route, because it is above them all', () => {
    for (const area of AREAS) {
      const { unmount } = render(
        <ImpersonationBanner
          viewer={viewerAt('viewer', { impersonating: true, impersonatedBy: 'admin' })}
          locale="en"
        />,
      );
      expect(screen.getByTestId('impersonation'), area.id).toBeInTheDocument();
      unmount();
    }
  });
});

describe('the notification centre', () => {
  const ITEMS: readonly AttentionItem[] = [
    {
      id: 'apr-0001',
      kind: 'approval',
      title: 'Reclaim 41 GiB on local-lvm',
      detail: 'awaiting decision',
      href: '/approvals/apr-0001',
      since: '2026-08-07T09:46:00+00:00',
    },
    {
      id: 'run-0007',
      kind: 'failure',
      title: 'Backup coverage gap',
      detail: 'failed',
      href: '/runs/run-0007',
      since: '2026-08-07T11:39:00+00:00',
    },
  ];

  it('says how many are waiting', () => {
    render(<NotificationCentre open locale="en" items={ITEMS} onClose={nothing} />);
    expect(screen.getByTestId('notification-count')).toHaveTextContent('2');
    expect(screen.getAllByTestId('notification')).toHaveLength(2);
  });

  it('marks the one that has been waiting longest', () => {
    render(<NotificationCentre open locale="en" items={ITEMS} onClose={nothing} />);
    const oldest = screen
      .getAllByTestId('notification')
      .filter((item) => item.getAttribute('data-oldest') === 'true');

    expect(oldest).toHaveLength(1);
    expect(oldest[0]).toHaveAttribute('data-item', 'apr-0001');
  });

  it('says nothing is waiting rather than showing an empty box', () => {
    render(<NotificationCentre open locale="en" items={[]} onClose={nothing} />);
    expect(screen.getByTestId('notifications-empty')).toBeInTheDocument();
  });

  it('is not in the document at all while it is closed', () => {
    render(
      <NotificationCentre open={false} locale="en" items={ITEMS} onClose={nothing} />,
    );
    expect(screen.queryByTestId('notifications')).toBeNull();
  });
});
