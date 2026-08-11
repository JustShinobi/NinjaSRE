import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { serveScenario } from '../support/dataset';

/**
 * The queue as a reviewer meets it.
 *
 * Four things per row, always in the same order: what would change, why, the
 * evidence, and a link back to the investigation. The link is the one that is
 * easy to leave out and hardest to do without — a reviewer who cannot reach the
 * run cannot check the claim, and a proposal nobody can check is one that gets
 * approved because disagreeing with it would cost twenty minutes.
 *
 * The acceptance figure carries both numbers rather than a percentage, because
 * sixty per cent of five and sixty per cent of two hundred are different facts.
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

async function renderQueue(): Promise<void> {
  const { default: Page } = await import('@/app/(shell)/proposals/page');
  render(await Page({ searchParams: Promise.resolve({}) }));
}

describe('the proposal queue', () => {
  it('lists every waiting proposal with its kind', async () => {
    await renderQueue();

    const items = screen.getAllByTestId('proposal-item');
    expect(items.length).toBeGreaterThan(0);
    expect(items.map((item) => item.getAttribute('data-kind'))).toContain('detector');
  });

  it('links each proposal back to the investigation that produced it', async () => {
    await renderQueue();

    const links = screen.getAllByTestId('origin-run');
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link.getAttribute('href')).toMatch(/^\/runs\/run-/);
    }
  });

  it('shows the evidence beside the reason rather than behind a click', async () => {
    await renderQueue();

    expect(screen.getByText(/had to rediscover it/)).toBeInTheDocument();
    expect(screen.getByText('run-0003/turn-2')).toBeInTheDocument();
  });

  it('resurfaces what was said the last time this was refused', async () => {
    await renderQueue();

    const prior = screen.getByTestId('prior-rejections');
    expect(prior).toHaveTextContent(/snapshot window runs nightly/);
  });

  it('reports the acceptance rate as both numbers', async () => {
    await renderQueue();

    expect(screen.getByTestId('acceptance')).toHaveTextContent('3 of 5');
  });
});

describe('a deployment nobody has proposed anything to', () => {
  it('says so as an empty state rather than as an error', async () => {
    serveScenario('empty');

    await renderQueue();

    expect(screen.getByText('The agent has proposed nothing')).toBeInTheDocument();
    expect(screen.queryAllByTestId('proposal-item')).toHaveLength(0);
  });
});
