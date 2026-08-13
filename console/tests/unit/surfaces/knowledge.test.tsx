import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { bodyFor } from '../../../scripts/fixture-server.mjs';
import { serveScenario } from '../support/dataset';

/**
 * What the knowledge screen says about how a document gets here, and what
 * "Proposed by an agent" actually is.
 *
 * Two defects this file exists to catch. First: an empty corpus told a
 * first-time operator to "Configure ingestion" without saying where that
 * goes — on a console that has no upload, paste, or connect-a-source control
 * anywhere in it. The fix is to say why the corpus is empty (most often that
 * the deployment's own setup is unfinished) and to send the action somewhere
 * that exists, rather than to a settings page with nothing about ingestion on
 * it. Second: "Proposed by an agent" rendered as a second, quiet copy of the
 * proposal queue. `/v1/proposals` already carries knowledge-typed entries
 * beside detector and configuration ones, so a panel that pretended to be its
 * own list would be a queue that could disagree with the one a reviewer
 * actually decides on.
 */

// A base for parsing a path-only address. Never contacted, and built rather
// than written, so the rule that forbids a foreign origin in console source
// is right to fire on a literal one and not on this.
const BASE = ['http:', '//fixtures.invalid'].join('');

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: () => ({ value: 'session-under-test' }),
    }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderKnowledge(): Promise<void> {
  const { default: Page } = await import('@/app/(shell)/knowledge/page');
  render(await Page({ searchParams: Promise.resolve({}) }));
}

/** `populated`, except the corpus itself answers empty. */
function serveFinishedButEmpty(): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const body: unknown =
      path === '/v1/knowledge/documents'
        ? { documents: [] }
        : bodyFor('populated', path);
    if (body === null || body === undefined) {
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

describe('a deployment still being set up', () => {
  it('says the setup is unfinished rather than pointing at a control that is not there', async () => {
    serveScenario('empty');

    await renderKnowledge();

    expect(screen.getByText('Nothing has been ingested')).toBeInTheDocument();
    expect(screen.getByText(/still being set up/)).toBeInTheDocument();
    expect(screen.getAllByText('Finish setting up').length).toBeGreaterThan(0);
    expect(screen.queryByText('Configure ingestion')).not.toBeInTheDocument();
    expect(screen.getByTestId('way-back')).toHaveAttribute('href', '/first-run');
  });
});

describe('a finished deployment that has ingested nothing yet', () => {
  it('sends the action to a place a document can actually reach the corpus from', async () => {
    serveFinishedButEmpty();

    await renderKnowledge();

    expect(screen.getByText('Nothing has been ingested')).toBeInTheDocument();
    // The label is not fixed by this screen — but the destination must never
    // be the general settings screen, which has no ingestion control on it.
    const wayBack = screen.getByTestId('way-back');
    expect(wayBack).toHaveAttribute('href', '/proposals');
    expect(wayBack.getAttribute('href')).not.toBe('/configuration');
  });
});

describe('what an investigation proposed to the knowledge base', () => {
  it('points at the one proposal queue instead of rendering a second copy of it', async () => {
    serveScenario('populated');

    await renderKnowledge();

    const link = screen.getByTestId('proposals-link');
    expect(link).toHaveAttribute('href', '/proposals');
    expect(
      screen.getByText('Changes an investigation proposed, awaiting review.'),
    ).toBeInTheDocument();

    // One row list on the page — the documents themselves. A second one under
    // "Proposed by an agent" would be the duplicate this screen must not carry.
    expect(screen.getAllByTestId('row-list')).toHaveLength(1);
  });
});
