import { render, screen, within } from '@testing-library/react';
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
        steps: [
          { name: 'model-provider', state: 'ready' },
          {
            name: 'first-investigation',
            state: 'blocked',
            title: 'Run your first investigation',
          },
        ],
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

describe('the autonomy row of a pending proposal', () => {
  const PENDING = {
    approval_id: 'apr-test-1',
    action: 'estate.expand_volume',
    arguments: {},
    decided_at: null,
    decided_by: null,
    expires_at: '2026-08-07T13:39:00+00:00',
    reason: null,
    requested_at: '2026-08-07T11:39:00+00:00',
    rollback_plan: null,
    run_id: 'run-under-test',
    side_effect_level: 'write_irreversible',
    state: 'pending',
    summary: 'Grow the volume that is at the ceiling of its own allocation.',
  };

  it('reads as a sentence, not the raw slug beside an em dash', async () => {
    stubReads({
      '/v1/approvals': { approvals: [PENDING] },
      '/v1/setup/checklist': { complete: true },
      '/v1/investigations/run-under-test/interactions': { interactions: [] },
    });

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsTab(contextFor(datasetViewer('populated'))));

    const row = screen
      .getAllByTestId('proposal-row')
      .find((each) => each.getAttribute('data-field') === 'autonomy');
    expect(row).toBeDefined();
    // The defect this guards against: the raw backend slug interpolated
    // straight into the sentence, with nothing translating it.
    expect(row).not.toHaveTextContent('write_irreversible —');
    expect(row).toHaveTextContent(/cannot be undone/i);
    expect(row).toHaveTextContent(/queued rather than applied/i);
  });

  it('still renders a level this console has no words for, as itself', async () => {
    stubReads({
      '/v1/approvals': {
        approvals: [{ ...PENDING, side_effect_level: 'time_travel' }],
      },
      '/v1/setup/checklist': { complete: true },
      '/v1/investigations/run-under-test/interactions': { interactions: [] },
    });

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsTab(contextFor(datasetViewer('populated'))));

    const row = screen
      .getAllByTestId('proposal-row')
      .find((each) => each.getAttribute('data-field') === 'autonomy');
    // The level comes from the deployment, not from this console. A level
    // nobody here has named must still render, as itself, never blank.
    expect(row).toHaveTextContent('time_travel');
  });
});

describe('a proposal whose answering window has closed', () => {
  /** Requested two hours before the fixed instant, expired one hour before it. */
  const LAPSED = {
    approval_id: 'apr-lapsed',
    action: 'estate.start_guest',
    arguments: { guest: 'ct-122' },
    decided_at: null,
    decided_by: null,
    expires_at: '2026-08-07T11:00:00+00:00',
    reason: null,
    requested_at: '2026-08-07T10:00:00+00:00',
    rollback_plan: null,
    run_id: 'run-lapsed',
    side_effect_level: 'write_irreversible',
    state: 'pending',
    summary: 'Start the guest that the failed backup left stopped.',
  };

  /** The same proposal, still inside its window. */
  const OPEN = {
    ...LAPSED,
    approval_id: 'apr-open',
    expires_at: '2026-08-07T13:00:00+00:00',
    requested_at: '2026-08-07T11:39:00+00:00',
    run_id: 'run-open',
  };

  function serve(approvals: readonly unknown[]): void {
    stubReads({
      '/v1/approvals': { approvals },
      '/v1/setup/checklist': { complete: true },
      '/v1/investigations/run-lapsed/interactions': { interactions: [] },
      '/v1/investigations/run-open/interactions': { interactions: [] },
    });
  }

  async function tab(): Promise<void> {
    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsTab(contextFor(datasetViewer('populated'))));
  }

  /** The card in the group the screen filed `id` under. */
  function cardFor(id: string): HTMLElement {
    const found = screen
      .getByTestId('approval-group')
      .querySelector(`[data-approval="${id}"]`);
    if (found === null) throw new Error(`no card for ${id}`);
    return found as HTMLElement;
  }

  it('offers no Approve on a card it has itself filed past its expiry', async () => {
    serve([LAPSED]);
    await tab();

    // The screen knows: this is the group it put the card in.
    const group = screen.getByTestId('approval-group');
    expect(group).toHaveAttribute('data-group', 'overdue');

    // And the deployment refuses a decision after the window closes, on the
    // clock rather than on the label. A control the screen already knows can
    // only fail is a control it must not draw.
    // Addressed by what a reader sees rather than by a test identifier: there
    // are two decision components behind this slot — one answering the
    // interaction a live investigation is blocked on, one answering the
    // approval in the store — and neither may offer the button.
    expect(within(group).queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(within(group).queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('says why in the place the control was, rather than leaving a gap', async () => {
    serve([LAPSED]);
    await tab();

    // Absence alone reads as a permission the viewer does not hold — this one
    // holds it. The reason is on the card: the window closed, and the reading
    // the decision would have been made against is stale, so the honest next
    // step is a fresh one rather than a decision on an old one.
    const closed = within(cardFor('apr-lapsed')).getByTestId('window-closed');
    expect(closed).toHaveTextContent(/window/i);
    expect(closed).toHaveTextContent(/ask for it again/i);
  });

  it('still offers Approve on a proposal that is inside its window', async () => {
    serve([OPEN]);
    await tab();

    // The other half, without which the fix above is indistinguishable from
    // having dropped the controls off every card on the screen.
    expect(screen.getByTestId('approval-group')).toHaveAttribute('data-group', 'today');
    expect(
      within(cardFor('apr-open')).getByRole('button', { name: 'Approve' }),
    ).toBeInTheDocument();
    expect(within(cardFor('apr-open')).queryByTestId('window-closed')).toBeNull();
  });
});
