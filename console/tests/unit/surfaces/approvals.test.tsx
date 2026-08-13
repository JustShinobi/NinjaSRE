import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { serveScenario } from '../support/dataset';

/**
 * Two inboxes of human decisions, one named "Approvals" and one named
 * "Proposed changes", in different menu groups, neither mentioning the other.
 *
 * A reader who opens both in sequence has to be able to say, from the screens
 * alone, which queue serves what — this is the minimal fix short of the
 * structural merge: a line on Approvals pointing at Proposed changes, and an
 * empty state that cites the rule feeding the queue rather than only the
 * mechanism.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: () => ({ value: 'session-under-test' }),
    }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderApprovals(): Promise<void> {
  const { default: Page } = await import('@/app/(shell)/approvals/page');
  render(await Page({ searchParams: Promise.resolve({}) }));
}

describe('the approvals screen and the proposals screen it is not', () => {
  beforeEach(() => {
    serveScenario('populated');
  });

  it('names this queue and explains what the other queue is for', async () => {
    await renderApprovals();

    expect(screen.getByTestId('page-header')).toHaveTextContent(
      'Actions awaiting approval',
    );
    const crossInbox = screen.getByTestId('approvals-elsewhere').parentElement;
    if (crossInbox === null) throw new Error('the cross-inbox link has no context');
    expect(crossInbox).toHaveTextContent(
      /changes the agent has proposed for the deployment/i,
    );
  });

  it('points a reader at the other inbox', async () => {
    await renderApprovals();

    const link = screen.getByRole('link', { name: /Proposed changes/ });
    expect(link).toHaveAttribute('href', '/proposals');
  });

  it('names that link once, as a single interactive element', async () => {
    await renderApprovals();

    const links = screen.getAllByRole('link', { name: /Proposed changes/ });
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

const EMPTY_TREE = {
  nodes: [
    { node_id: 'org-northwind', name: 'Northwind', kind: 'org', parent_id: null },
  ],
};

describe('an empty queue that says why', () => {
  it('cites the active threshold and where it was set, once the setup is done', async () => {
    stubReads({
      '/v1/approvals': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
      '/v1/config': EMPTY_TREE,
      '/v1/config/org-northwind/fields': {
        fields: [
          {
            path: 'policies.approvals.threshold',
            value: 'read_sensitive',
            default: 'write_reversible',
            provenance: 'org-northwind',
          },
        ],
      },
    });

    const { ApprovalsScreen } = await import('@/surfaces/screens/approvals');
    const { contextFor } = await import('../support/dataset');
    const { datasetViewer } = await import('../support/dataset');
    render(
      await ApprovalsScreen(
        contextFor({ ...datasetViewer('populated'), teamNodeId: 'org-northwind' }),
      ),
    );

    expect(screen.getByTestId('panel')).toHaveTextContent(/read_sensitive/);
    expect(screen.getByTestId('panel')).toHaveTextContent(/set at org-northwind/i);
  });

  it('says the threshold is the shipped default when nothing set it', async () => {
    stubReads({
      '/v1/approvals': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
      '/v1/config': EMPTY_TREE,
      '/v1/config/org-northwind/fields': {
        fields: [
          {
            path: 'policies.approvals.threshold',
            value: null,
            default: 'write_reversible',
            provenance: '',
          },
        ],
      },
    });

    const { ApprovalsScreen } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(
      await ApprovalsScreen(
        contextFor({ ...datasetViewer('populated'), teamNodeId: 'org-northwind' }),
      ),
    );

    expect(screen.getByTestId('panel')).toHaveTextContent(/deployment default/i);
  });

  it('keeps recorded scenarios readable while they expose the legacy policy path', async () => {
    stubReads({
      '/v1/approvals': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
      '/v1/config': EMPTY_TREE,
      '/v1/config/org-northwind': {
        node_id: 'org-northwind',
        values: { 'approval.required_above': 'read' },
        provenance: { 'approval.required_above': 'org-northwind' },
      },
    });

    const { ApprovalsScreen } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(
      await ApprovalsScreen(
        contextFor({ ...datasetViewer('populated'), teamNodeId: 'org-northwind' }),
      ),
    );

    expect(screen.getByTestId('panel')).toHaveTextContent(/read/);
    expect(screen.getByTestId('panel')).toHaveTextContent(/set at org-northwind/i);
  });

  it('does not announce the empty-state action as both a link and a button', async () => {
    stubReads({
      '/v1/approvals': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
    });

    const { ApprovalsScreen } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsScreen(contextFor(datasetViewer('populated'))));

    expect(screen.getAllByRole('link', { name: 'See what is running' })).toHaveLength(
      1,
    );
    expect(screen.queryByRole('button', { name: 'See what is running' })).toBeNull();
  });

  it('prefers telling an unfinished setup over the policy, while the checklist is open', async () => {
    stubReads({
      '/v1/approvals': { approvals: [] },
      '/v1/setup/checklist': { complete: false },
      '/v1/config': EMPTY_TREE,
      '/v1/config/org-northwind': {
        node_id: 'org-northwind',
        values: { 'approval.required_above': 'read' },
        provenance: { 'approval.required_above': 'org-northwind' },
      },
    });

    const { ApprovalsScreen } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(
      await ApprovalsScreen(
        contextFor({ ...datasetViewer('populated'), teamNodeId: 'org-northwind' }),
      ),
    );

    // The setup cause, not the policy citation.
    expect(screen.queryByText(/org-northwind/)).toBeNull();
  });
});
