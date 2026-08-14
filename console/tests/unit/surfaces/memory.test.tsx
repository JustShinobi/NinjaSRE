import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { LearnedTab } from '@/surfaces/screens/memory';

import { bodyFor } from '../../../scripts/fixture-server.mjs';
import { serveScenario } from '../support/dataset';

/**
 * Why the corpus is empty, and how far the empty state goes to say so.
 *
 * "An episode is written when an investigation ends. None has ended yet" is
 * true and, on its own, useless — it names the mechanism and stops one step
 * short of the reason. On this deployment the reason is always the same
 * unfinished setup that every other empty screen in the console already
 * blames, and this file exists so the memory screen says that too, with a
 * link, instead of leaving an operator to guess why nothing ever arrives.
 *
 * The second thing this guards is the shape of the page once that sentence is
 * true. Two panels that each spend most of a viewport restating one fact are
 * a page nobody reads to the end; collapsed to one section, the whole cycle
 * — investigation, episode, strategy — fits above the fold.
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
});

// A base for parsing a path-only address. Never contacted, and built rather
// than written — see `../support/dataset.ts`, which does the same for the
// same reason.
const BASE = ['http:', '//fixtures.invalid'].join('');

function okResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

/**
 * The `populated` dataset, with the episode corpus and the setup checklist
 * replaced by whatever this test needs to hold.
 *
 * Neither the committed `empty` nor `populated` scenario carries the
 * combination every case here needs — a finished setup with no episodes, or a
 * corpus shaped to test which filter has something to offer — so this builds
 * it from the same fixture table the dataset helper uses, overriding only the
 * two reads this screen makes decisions from.
 */
function serveMemory(overrides: { episodes?: unknown; checklist?: unknown }): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/v1/memory/search' && overrides.episodes !== undefined) {
      return Promise.resolve(okResponse(overrides.episodes));
    }
    if (path === '/v1/setup/checklist' && overrides.checklist !== undefined) {
      return Promise.resolve(okResponse(overrides.checklist));
    }
    const body: unknown = bodyFor('populated', path);
    if (body === null || body === undefined) {
      return Promise.resolve(
        new Response('{}', {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }
    return Promise.resolve(okResponse(body));
  });
}

async function renderMemory(): Promise<void> {
  render(await LearnedTab(await surfaceContext({})));
}

describe('a deployment where no investigation has ever ended', () => {
  it('names the unfinished setup as the reason, with a link that finishes it', async () => {
    serveScenario('empty');
    await renderMemory();

    // The mechanism stays — this is the part the spec says already works.
    expect(
      screen.getByText(/An episode is written when an investigation ends/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/A strategy is synthesised once enough episodes agree/),
    ).toBeInTheDocument();

    // And it closes with the real, local reason and a way out.
    expect(
      screen.getByText(/this deployment is still being set up/),
    ).toBeInTheDocument();
    // Four of the platform's own five steps, read from the checklist fixture
    // itself rather than from the console's seven-screen wizard sequencing.
    expect(screen.getByText(/4 step\(s\) are outstanding/)).toBeInTheDocument();

    const link = screen.getByTestId('way-back');
    expect(link).toHaveAttribute('href', '/first-run');
    expect(screen.getByRole('link', { name: 'Finish setting up' })).toBeInTheDocument();
  });

  it('collapses to a single section, not two panels of the same sentence', async () => {
    serveScenario('empty');
    await renderMemory();

    expect(screen.getAllByTestId('panel').length).toBe(1);
    expect(screen.queryByTestId('row-list')).toBeNull();
  });

  it('shows no filter, since the corpus behind it holds nothing', async () => {
    serveScenario('empty');
    await renderMemory();

    expect(screen.queryByTestId('filters')).toBeNull();
  });

  it('carries no orphaned "Episodes: N" counter beside the header', async () => {
    serveScenario('empty');
    await renderMemory();

    expect(screen.queryByText(/Episodes:\s*\d/)).toBeNull();
  });
});

describe('a deployment whose setup is finished but has not investigated yet', () => {
  it('points at what is running instead of at the setup', async () => {
    serveMemory({ episodes: { episodes: [] } });
    await renderMemory();

    expect(screen.queryByText(/still being set up/)).toBeNull();
    const link = screen.getByTestId('way-back');
    expect(link).toHaveAttribute('href', '/runs');
    expect(
      screen.getByRole('link', { name: 'See what is running' }),
    ).toBeInTheDocument();
  });
});

describe('a corpus with episodes in it', () => {
  it('keeps episodes and strategies as two panels', async () => {
    serveScenario('populated');
    await renderMemory();

    const panels = screen.getAllByTestId('panel');
    expect(panels.length).toBe(2);
    expect(screen.getByText('Episodes')).toBeInTheDocument();
    expect(screen.getByText('Strategies')).toBeInTheDocument();
    expect(screen.getAllByTestId('row').length).toBe(5);
  });

  it('carries no orphaned "Episodes: N" counter beside the header', async () => {
    serveScenario('populated');
    await renderMemory();

    expect(screen.queryByText(/Episodes:\s*\d/)).toBeNull();
  });

  it('still explains what a strategy is, in its own words, with no episode data', async () => {
    serveScenario('populated');
    await renderMemory();

    expect(
      screen.getByText(
        'A strategy is synthesised once enough episodes agree about what worked. Not enough have been recorded.',
      ),
    ).toBeInTheDocument();
  });
});

describe('a filter with nothing behind it but "Any"', () => {
  it('is hidden, while a filter with real choices stays', async () => {
    serveMemory({
      episodes: {
        episodes: [
          {
            episode_id: 'ep-a',
            title: 'A guest volume filled',
            outcome: 'resolved',
            components: [],
            occurred_at: '2026-08-01T00:00:00+00:00',
            run_id: 'run-a',
          },
          {
            episode_id: 'ep-b',
            title: 'Quorum lost its margin',
            outcome: 'unresolved',
            components: [],
            occurred_at: '2026-08-02T00:00:00+00:00',
            run_id: 'run-b',
          },
        ],
      },
    });
    await renderMemory();

    const filters = screen.getAllByTestId('filter');
    expect(
      filters.some((filter) => filter.getAttribute('data-filter') === 'outcome'),
    ).toBe(true);
    expect(
      filters.some((filter) => filter.getAttribute('data-filter') === 'component'),
    ).toBe(false);
  });
});
