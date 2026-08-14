import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { SignalsScreen } from '@/surfaces/screens/signals';

import { principalHolding, serveScenario } from '../support/dataset';

/**
 * Signals: the fusion of Detectors and Data into one screen, four tabs — what
 * enters continuous observation and where an alert ends up once it has, which
 * used to sit in different zones of the menu for no reason a reader could see.
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
  it('names the area Signals, whichever tab is open', async () => {
    await render_();

    expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', 'signals');
    expect(screen.getByTestId('page-header')).toHaveTextContent('Signals');
  });
});

describe('the tab bar', () => {
  it('offers all four tabs, in the order data moves through them', async () => {
    await render_();

    const tabs = screen.getAllByTestId('tab-link');
    expect(tabs.map((tab) => tab.getAttribute('data-tab'))).toEqual([
      'intake',
      'observation',
      'schedules',
      'destinations',
    ]);
  });

  it('defaults to Intake', async () => {
    await render_();

    expect(screen.getByTestId('ingress-sources')).toBeInTheDocument();
  });

  it('shows continuous observation — the detector table — on its own tab', async () => {
    await render_({ tab: 'observation' });

    expect(screen.getAllByTestId('detector').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('ingress-sources')).toBeNull();
  });

  it('shows destinations on its own tab', async () => {
    await render_({ tab: 'destinations' });

    expect(screen.getByTestId('destinations')).toBeInTheDocument();
    expect(screen.queryByTestId('ingress-sources')).toBeNull();
  });
});

describe('a viewer who may not manage schedules', () => {
  it('offers no Schedules tab at all, rather than one whose content is blank', async () => {
    serveScenario('populated', principalHolding(['config.read']));
    await render_();

    const tabs = screen.getAllByTestId('tab-link');
    expect(tabs.map((tab) => tab.getAttribute('data-tab'))).not.toContain('schedules');
  });

  it('falls back to Intake for a schedules tab requested directly in the address', async () => {
    serveScenario('populated', principalHolding(['config.read']));
    await render_({ tab: 'schedules' });

    expect(screen.getByTestId('ingress-sources')).toBeInTheDocument();
  });
});
