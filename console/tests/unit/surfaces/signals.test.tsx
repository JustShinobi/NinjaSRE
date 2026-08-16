import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { SignalsScreen } from '@/surfaces/screens/signals';

import { principalHolding, serveScenario } from '../support/dataset';

/**
 * Signals, after the dissolution: one tab left standing.
 *
 * Intake, Schedules and Destinations carried on as Settings pages of their
 * own (`settings-alert-intake.test.tsx`,
 * `settings-schedules-destinations.test.tsx`); nothing replaces continuous
 * observation yet, so this address keeps rendering exactly that, with no tab
 * chrome around a tab bar of one.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
  serveScenario('populated', principalHolding(['config.read', 'schedule.manage']));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function render_(search: Record<string, string> = {}): Promise<void> {
  render(await SignalsScreen(await surfaceContext(search)));
}

describe('the area header', () => {
  it('names the area Signals', async () => {
    await render_();

    expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', 'signals');
    expect(screen.getByTestId('page-header')).toHaveTextContent('Signals');
  });
});

describe('what renders at this address now', () => {
  it('shows continuous observation — the detector table — with no tab bar around it', async () => {
    await render_({ tab: 'observation' });

    expect(screen.getAllByTestId('detector').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('tab-links')).toBeNull();
  });

  it('shows the same thing whether or not the address still carries a tab', async () => {
    // The redirect that used to send every other variant of this address
    // elsewhere is `signals/page.tsx`'s own concern, not this screen's — by
    // the time `SignalsScreen` renders at all, there is only one tab left to
    // show, so it is what renders regardless of what the query still names.
    await render_();

    expect(screen.getAllByTestId('detector').length).toBeGreaterThan(0);
  });

  it('carries none of what moved to Settings pages of its own', async () => {
    await render_();

    expect(screen.queryByTestId('ingress-sources')).toBeNull();
    expect(screen.queryByTestId('destinations')).toBeNull();
    expect(screen.queryByTestId('schedules')).toBeNull();
  });
});
