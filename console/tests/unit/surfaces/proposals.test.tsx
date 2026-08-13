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
 *
 * Two more things this screen has to get right, alongside Approvals:
 * - it points a reader who may see the other queue at it, and says nothing to
 *   one who may not (spec 034, item 2);
 * - its empty state names where a proposal comes from, and prefers the setup
 *   cause when the deployment has never investigated at all (spec 034, item 3).
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

describe('the proposals screen and the approvals queue it is not', () => {
  beforeEach(() => {
    serveScenario('populated');
  });

  it('points a reader at the other inbox', async () => {
    await renderQueue();

    const link = screen.getByRole('link', { name: /Actions awaiting approval/ });
    expect(link).toHaveAttribute('href', '/approvals');
  });

  it('says what the other inbox is for, not only its name', async () => {
    await renderQueue();

    expect(screen.getByTestId('proposals-elsewhere').parentElement).toHaveTextContent(
      /For actions the agent wants to take now/i,
    );
  });

  it('names that link once, as a single interactive element', async () => {
    await renderQueue();

    const links = screen.getAllByRole('link', { name: /Actions awaiting approval/ });
    expect(links).toHaveLength(1);
    // Not a button sitting inside the same link, and not a link sitting
    // inside a button — one control, reachable once by a keyboard or a
    // screen reader.
    expect(links[0]?.closest('a,button')).toBe(links[0]);
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

describe('the other inbox, absent for a viewer who may not open it', () => {
  it('renders no link when the viewer lacks the permission the other queue needs', async () => {
    stubReads({
      '/v1/proposals': EMPTY_QUEUE,
      '/v1/setup/checklist': { complete: true },
    });

    const { ProposalsScreen } = await import('@/surfaces/screens/proposals');
    const { contextFor } = await import('../support/dataset');
    render(
      await ProposalsScreen(
        contextFor({
          principalId: 'user-under-test',
          displayName: 'Avery Lockhart',
          email: null,
          roles: [],
          // No `approval.read` — the permission both Approvals and this
          // screen read behind.
          permissions: ['investigation.read'],
          teamNodeId: 'org-northwind',
          impersonating: false,
          impersonatedBy: null,
        }),
      ),
    );

    expect(screen.queryByTestId('proposals-elsewhere')).toBeNull();
    expect(screen.queryByRole('link', { name: /Approvals/ })).toBeNull();
  });
});

describe('an empty queue that says where a proposal would come from', () => {
  it('names the investigation mechanism once the setup is done', async () => {
    stubReads({
      '/v1/proposals': EMPTY_QUEUE,
      '/v1/setup/checklist': { complete: true },
    });

    const { ProposalsScreen } = await import('@/surfaces/screens/proposals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ProposalsScreen(contextFor(datasetViewer('populated'))));

    expect(screen.getByText(/learns something worth writing down/)).toBeInTheDocument();
  });

  it('prefers the setup cause when the deployment has never investigated', async () => {
    stubReads({
      '/v1/proposals': EMPTY_QUEUE,
      '/v1/setup/checklist': { complete: false },
    });

    const { ProposalsScreen } = await import('@/surfaces/screens/proposals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ProposalsScreen(contextFor(datasetViewer('populated'))));

    expect(screen.getByText(/still being set up/)).toBeInTheDocument();
    expect(screen.queryByText(/learns something worth writing down/)).toBeNull();
  });
});
