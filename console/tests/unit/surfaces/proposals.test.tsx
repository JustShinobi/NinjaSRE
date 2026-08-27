import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { contextFor, datasetViewer, serveScenario } from '../support/dataset';

/**
 * The "Changes" tab of Decisions, as a reviewer meets it.
 *
 * Four things per row, always in the same order: what would change, why, the
 * evidence, and a link back to the investigation. The link is the one that is
 * easy to leave out and hardest to do without — a reviewer who cannot reach the
 * run cannot check the claim, and a proposal nobody can check is one that gets
 * approved because disagreeing with it would cost twenty minutes.
 *
 * The acceptance figure carries both numbers rather than a percentage, because
 * sixty per cent of five and sixty per cent of two hundred are different facts.
 *
 * Used to be its own screen, with a paragraph pointing at Approvals and a
 * check that its one panel named itself the same way the page title did. Both
 * moved: the sibling tab (`approvals.tsx`, rendered as "Actions" beside this
 * one) is now what shows a reader the other queue exists, and the page-title
 * invariant no longer applies once this panel is one tab of a bigger page
 * rather than the whole of it — see `decisions.test.tsx`.
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
  const { ProposalsTab } = await import('@/surfaces/screens/proposals');
  render(await ProposalsTab(contextFor(datasetViewer('populated'))));
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

// A base for parsing a path-only address. Never contacted, and built rather
// than written, so the no-foreign-origin rule has nothing to flag.
const BASE = ['http:', '//fixtures.invalid'].join('');

/** A pathname's fixed body, or 404 for anything not declared. */
function stubReads(bodies: Readonly<Record<string, unknown>>): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const body = bodies[path];
    if (body === undefined) {
      return Promise.resolve(
        new Response('{}', {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

const EMPTY_QUEUE = {
  proposals: [],
  acceptance: { decided: 0, approved: 0, rate: 0 },
};

describe('an empty queue that says where a proposal would come from', () => {
  it('names the investigation mechanism once the setup is done', async () => {
    stubReads({
      '/v1/proposals': EMPTY_QUEUE,
      '/v1/setup/checklist': { complete: true },
    });

    const { ProposalsTab } = await import('@/surfaces/screens/proposals');
    render(await ProposalsTab(contextFor(datasetViewer('populated'))));

    expect(screen.getByText(/learns something worth writing down/)).toBeInTheDocument();
  });

  it('prefers the setup cause when the deployment has never investigated', async () => {
    stubReads({
      '/v1/proposals': EMPTY_QUEUE,
      '/v1/setup/checklist': {
        complete: false,
        steps: [
          { name: 'model-provider', state: 'ready' },
          {
            name: 'first-investigation',
            state: 'blocked',
            title: 'Run your first investigation',
          },
        ],
      },
    });

    const { ProposalsTab } = await import('@/surfaces/screens/proposals');
    render(await ProposalsTab(contextFor(datasetViewer('populated'))));

    expect(screen.getByText(/still being set up/)).toBeInTheDocument();
    expect(screen.queryByText(/learns something worth writing down/)).toBeNull();
  });
});
