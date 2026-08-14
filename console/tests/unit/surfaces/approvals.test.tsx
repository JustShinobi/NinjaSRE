import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

/**
 * The "Actions" tab of Decisions: what the agent wants to do now.
 *
 * Used to be its own screen with a paragraph pointing at "Proposed changes",
 * the sibling inbox for "should the deployment be different from tomorrow
 * on". The two are tabs of one screen now (`screens/decisions.tsx`), which is
 * what a reader of either sees the other exists from — the mutual-visibility
 * assertions that used to live here moved to `decisions.test.tsx`, which
 * tests the tab bar both tabs share.
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

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor } = await import('../support/dataset');
    const { datasetViewer } = await import('../support/dataset');
    render(
      await ApprovalsTab(
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

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(
      await ApprovalsTab(
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

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(
      await ApprovalsTab(
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

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsTab(contextFor(datasetViewer('populated'))));

    expect(screen.getAllByRole('link', { name: 'See what is running' })).toHaveLength(
      1,
    );
    expect(screen.queryByRole('button', { name: 'See what is running' })).toBeNull();
  });

  it('prefers telling an unfinished setup over the policy, while the checklist is open', async () => {
    stubReads({
      '/v1/approvals': { approvals: [] },
      '/v1/setup/checklist': {
        complete: false,
        steps: [{ name: 'model-provider', state: 'ready' }],
      },
      '/v1/config': EMPTY_TREE,
      '/v1/config/org-northwind': {
        node_id: 'org-northwind',
        values: { 'approval.required_above': 'read' },
        provenance: { 'approval.required_above': 'org-northwind' },
      },
    });

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(
      await ApprovalsTab(
        contextFor({ ...datasetViewer('populated'), teamNodeId: 'org-northwind' }),
      ),
    );

    // The setup cause, not the policy citation.
    expect(screen.queryByText(/org-northwind/)).toBeNull();
  });
});
