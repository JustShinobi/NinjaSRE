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
function serveMemory(overrides: {
  episodes?: unknown;
  checklist?: unknown;
  runs?: unknown;
}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/v1/memory/search' && overrides.episodes !== undefined) {
      return Promise.resolve(okResponse(overrides.episodes));
    }
    if (path === '/v1/setup/checklist' && overrides.checklist !== undefined) {
      return Promise.resolve(okResponse(overrides.checklist));
    }
    if (path === '/v1/runs' && overrides.runs !== undefined) {
      return Promise.resolve(okResponse(overrides.runs));
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

    // And it closes with the real, local reason and a way out — naming the
    // step this screen's own cause depends on (the mock plane's own title
    // for it, "Watch it look") rather than a bare count.
    expect(
      screen.getByText(/this deployment is still being set up/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Watch it look/)).toBeInTheDocument();
    expect(screen.queryByText(/cannot run until/i)).toBeNull();

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
    // The run list is served empty deliberately. This case is "nothing has
    // been investigated", and the sentence it asserts is only true while
    // that holds — reading the populated dataset's fifty finished runs here
    // would have been the screen describing a deployment other than the one
    // the fixture set up.
    serveMemory({ episodes: { episodes: [] }, runs: { runs: [] } });
    await renderMemory();

    expect(screen.queryByText(/still being set up/)).toBeNull();
    const link = screen.getByTestId('way-back');
    expect(link).toHaveAttribute('href', '/runs');
    expect(
      screen.getByRole('link', { name: 'See what is running' }),
    ).toBeInTheDocument();
  });
});

/**
 * The case the whole cause exists for: the chain above the corpus plainly ran.
 *
 * A deployment that has finished fifty investigations and holds no episodes is
 * not a deployment waiting for its first one, and the sentence it was showing
 * — "none has been written yet" — read as patience while every attempt to
 * write one was failing. Nobody would ever have gone looking, because the
 * screen said the thing that means "come back later".
 */
describe('a deployment that has investigated and written nothing down', () => {
  const finished = {
    runs: [
      { run_id: 'run-a', status: 'completed', started_at: '2026-01-01T00:00:00Z' },
      { run_id: 'run-b', status: 'completed', started_at: '2026-01-02T00:00:00Z' },
      { run_id: 'run-c', status: 'failed', started_at: '2026-01-03T00:00:00Z' },
    ],
  };

  it('counts the investigations that finished instead of saying none has', async () => {
    serveMemory({ episodes: { episodes: [] }, runs: finished });
    await renderMemory();

    // Two, not three: the failed run had no conclusion to extract from, so
    // counting it would blame the corpus for a gap nothing was going to fill.
    expect(screen.getByText(/2 investigations have finished/)).toBeInTheDocument();
    expect(screen.queryByText(/still being set up/)).toBeNull();
  });

  it('sends the reader to the model each role uses', async () => {
    serveMemory({ episodes: { episodes: [] }, runs: finished });
    await renderMemory();

    expect(screen.getByTestId('way-back')).toHaveAttribute(
      'href',
      '/settings/models-providers',
    );
  });

  it('names no failure the console cannot read', async () => {
    serveMemory({ episodes: { episodes: [] }, runs: finished });
    await renderMemory();

    expect(screen.queryByText(/connection error/i)).toBeNull();
    expect(screen.queryByText(/credential/i)).toBeNull();
  });

  it('still explains the mechanism, which is what the reader needs first', async () => {
    serveMemory({ episodes: { episodes: [] }, runs: finished });
    await renderMemory();

    expect(
      screen.getByText(/An episode is written when an investigation ends/),
    ).toBeInTheDocument();
  });
});

describe('a corpus with episodes in it', () => {
  it('draws one card per episode, never a Strategies panel the artboard does not show', async () => {
    serveScenario('populated');
    await renderMemory();

    expect(screen.getAllByTestId('episode-card').length).toBe(5);
    expect(screen.queryByText('Strategies')).toBeNull();
  });

  it('carries no orphaned "Episodes: N" counter beside the header', async () => {
    serveScenario('populated');
    await renderMemory();

    expect(screen.queryByText(/Episodes:\s*\d/)).toBeNull();
  });
});

describe('an episode leads with its human phrase, never the machine key', () => {
  const EPISODE = {
    episode_id: 'ep-9',
    title: 'workload_stopped: The runner guest stopped and stayed down',
    summary: 'The guest was stopped administratively and nothing restarted it.',
    outcome: 'resolved',
    components: ['service:runner-orchestrator', 'node:pve02'],
    occurred_at: '2026-08-07T09:00:00Z',
    run_id: 'run-77',
  };

  it('moves a known machine prefix into the meta line, in mono', async () => {
    serveMemory({ episodes: { episodes: [EPISODE] } });
    await renderMemory();

    expect(screen.getByTestId('episode-title')).toHaveTextContent(
      'The runner guest stopped and stayed down',
    );
    expect(screen.getByTestId('episode-title')).not.toHaveTextContent(
      'workload_stopped',
    );
    const meta = screen.getByTestId('episode-meta');
    expect(meta).toHaveTextContent('workload_stopped');
    expect(meta).toHaveTextContent('runner-orchestrator');
  });

  it('leaves a title whose prefix is not a machine word exactly as written', async () => {
    serveMemory({
      episodes: {
        episodes: [{ ...EPISODE, title: 'Quorum: two of two votes, no margin' }],
      },
    });
    await renderMemory();

    expect(screen.getByTestId('episode-title')).toHaveTextContent(
      'Quorum: two of two votes, no margin',
    );
  });

  it('prints component chips by their short display name, raw spelling as tooltip', async () => {
    serveMemory({ episodes: { episodes: [EPISODE] } });
    await renderMemory();

    const chips = screen.getAllByTestId('episode-component-chip');
    expect(chips.map((chip) => chip.textContent)).toEqual([
      'runner-orchestrator',
      'pve02',
    ]);
    expect(chips[0]).toHaveAttribute('title', 'service:runner-orchestrator');
  });

  it('words the outcome filter with the same vocabulary the chip already uses', async () => {
    serveMemory({
      episodes: {
        episodes: [
          EPISODE,
          { ...EPISODE, episode_id: 'ep-10', outcome: 'inconclusive' },
        ],
      },
    });
    await renderMemory();

    // Never the raw store word in the filter: the chip says "Inconclusive"
    // through the episode vocabulary, and the filter says the same.
    const filter = screen.getByLabelText(/outcome/i);
    expect(filter.textContent).toContain('Inconclusive');
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

    // The outcome control renders (two real outcomes among the episodes);
    // the component filter does not (every episode carries an empty
    // components list) -- the same "furniture" rule the incidents screen's
    // segmented controls follow.
    expect(screen.getByLabelText('Outcome')).toBeInTheDocument();
    expect(screen.queryByTestId('component-filter')).toBeNull();
  });
});
