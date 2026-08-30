import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { contextFor, datasetViewer, serveScenario } from '../support/dataset';

/**
 * Decisions: the fusion of Approvals and Proposed changes into one screen,
 * two tabs, so a reader of either sees the other exists without a
 * cross-link paragraph doing the work the tab bar now does.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: () => ({ value: 'session-under-test' }),
    }),
}));

beforeEach(() => {
  serveScenario('populated');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function render_(search = ''): Promise<void> {
  const { DecisionsScreen } = await import('@/surfaces/screens/decisions');
  render(await DecisionsScreen(contextFor(datasetViewer('populated'), search)));
}

describe('the area header', () => {
  it('names the area Decisions, once, for both tabs', async () => {
    await render_();
    expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', 'decisions');
    expect(screen.getByTestId('page-header')).toHaveTextContent('Decisions');
  });
});

describe('the tab bar', () => {
  it('offers both tabs, actions first', async () => {
    await render_();

    const tabs = screen.getAllByTestId('tab-link');
    expect(tabs.map((tab) => tab.getAttribute('data-tab'))).toEqual([
      'actions',
      'changes',
    ]);
    expect(tabs[0]).toHaveAttribute('href', '?tab=actions');
    expect(tabs[1]).toHaveAttribute('href', '?tab=changes');
  });

  it('defaults to Actions — what the agent wants to do now', async () => {
    await render_();

    expect(screen.getAllByTestId('decision-card').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('proposal-item')).toBeNull();
  });

  it('shows Changes proposed when the address asks for it, and nothing from Actions', async () => {
    await render_('tab=changes');

    expect(screen.getAllByTestId('proposal-item').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('decision-card')).toBeNull();
  });

  it('marks the requested tab current in the tab bar itself', async () => {
    await render_('tab=changes');

    const tabs = screen.getAllByTestId('tab-link');
    const current = tabs.find((tab) => tab.getAttribute('data-tab') === 'changes');
    expect(current).toHaveAttribute('aria-current', 'page');
  });

  it('falls back to Actions for a tab name the address does not carry', async () => {
    await render_('tab=nonsense');

    expect(screen.getAllByTestId('decision-card').length).toBeGreaterThan(0);
  });
});

describe('reading either tab reveals the other exists', () => {
  it('names both tabs on the page at once, regardless of which is selected', async () => {
    await render_();

    const bar = screen.getByTestId('tab-links');
    expect(within(bar).getByText('Actions')).toBeInTheDocument();
    expect(within(bar).getByText('Changes')).toBeInTheDocument();
  });
});
