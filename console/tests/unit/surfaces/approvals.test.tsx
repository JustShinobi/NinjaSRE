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

/**
 * A pathname's fixed body, or 404 for anything not declared.
 *
 * A key carrying a query string (`/v1/approvals?state=pending`) is matched
 * against the full address; a bare pathname key is matched against every
 * query string that reaches it, including none — which is what lets a test
 * that does not care about `state=` stub one body for all three of
 * ApprovalsTab's reads.
 */
function stubReads(bodies: Readonly<Record<string, unknown>>): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const url = new URL(String(input), BASE);
    const full = `${url.pathname}${url.search}`;
    const body = full in bodies ? bodies[full] : bodies[url.pathname];
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

describe('the autonomy line of a pending decision', () => {
  const PENDING = {
    approval_id: 'apr-test-1',
    action: 'estate.expand_volume',
    arguments: {},
    autonomy: {
      side_effect_level: 'write_irreversible',
      reversible: false,
      queued: true,
    },
    decided_at: null,
    decided_by: null,
    expires_at: '2026-08-07T13:39:00+00:00',
    reason: null,
    requested_at: '2026-08-07T11:39:00+00:00',
    rollback_plan: null,
    rollback: [],
    steps: [],
    evidence: [],
    blast_radius: { known: false },
    risk: { class: 'medium', score: 3, scale: 5 },
    origin: { run_id: 'run-under-test' },
    run_id: 'run-under-test',
    side_effect_level: 'write_irreversible',
    state: 'pending',
    title: 'Grow the volume that is at the ceiling of its own allocation.',
    summary: 'Grow the volume that is at the ceiling of its own allocation.',
  };

  it('reads as a sentence, not the raw slug beside an em dash', async () => {
    stubReads({
      '/v1/approvals?state=pending': { approvals: [PENDING] },
      '/v1/approvals?state=expired': { approvals: [] },
      '/v1/approvals?state=decided&limit=10': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
      '/v1/investigations/run-under-test/interactions': { interactions: [] },
    });

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsTab(contextFor(datasetViewer('populated'))));

    const autonomy = screen
      .getAllByTestId('decision-section')
      .find((each) => each.getAttribute('data-section') === 'autonomy');
    expect(autonomy).toBeDefined();
    // The defect this guards against: the raw backend slug interpolated
    // straight into the sentence, with nothing translating it.
    expect(autonomy).not.toHaveTextContent('write_irreversible —');
    // One phrase, one frame: the short worded level, one dash, the queue
    // promise — never the level's own full sentence composed into a second
    // dash ("… cannot be undone. — queued …").
    expect(autonomy).toHaveTextContent(/irreversible/i);
    expect(autonomy).toHaveTextContent(/queued/i);
    expect((autonomy?.textContent?.match(/—/g) ?? []).length).toBe(1);
  });

  it('prints a bare call signature as code, never dressed as prose', async () => {
    stubReads({
      '/v1/approvals?state=pending': {
        approvals: [
          {
            ...PENDING,
            steps: [
              {
                ordinal: 1,
                summary: "proxmox_start_guest(kind='lxc', vmid=102)",
                capability: 'proxmox_start_guest',
              },
            ],
          },
        ],
      },
      '/v1/approvals?state=expired': { approvals: [] },
      '/v1/approvals?state=decided&limit=10': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
      '/v1/investigations/run-under-test/interactions': { interactions: [] },
    });

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsTab(contextFor(datasetViewer('populated'))));

    const signature = screen.getAllByTestId('step-signature')[0];
    expect(signature?.tagName).toBe('CODE');
    expect(signature).toHaveClass('truncate');
  });

  it('still renders a level this console has no words for, as itself', async () => {
    stubReads({
      '/v1/approvals?state=pending': {
        approvals: [
          {
            ...PENDING,
            side_effect_level: 'time_travel',
            autonomy: {
              side_effect_level: 'time_travel',
              reversible: false,
              queued: true,
            },
          },
        ],
      },
      '/v1/approvals?state=expired': { approvals: [] },
      '/v1/approvals?state=decided&limit=10': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
      '/v1/investigations/run-under-test/interactions': { interactions: [] },
    });

    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsTab(contextFor(datasetViewer('populated'))));

    const autonomy = screen
      .getAllByTestId('decision-section')
      .find((each) => each.getAttribute('data-section') === 'autonomy');
    // The level comes from the deployment, not from this console. A level
    // nobody here has named must still render, as itself, never blank.
    expect(autonomy).toHaveTextContent('time_travel');
  });
});

describe('a decision whose answering window has closed', () => {
  const BASE_FIELDS = {
    action: 'estate.start_guest',
    arguments: { guest: 'ct-122' },
    autonomy: {
      side_effect_level: 'write_irreversible',
      reversible: true,
      queued: true,
    },
    decided_at: null,
    decided_by: null,
    reason: null,
    rollback_plan: null,
    rollback: [],
    steps: [],
    evidence: [],
    blast_radius: { known: false },
    risk: { class: 'medium', score: 3, scale: 5 },
    side_effect_level: 'write_irreversible',
    summary: 'Start the guest that the failed backup left stopped.',
    title: 'Start the guest that the failed backup left stopped.',
  };

  /** Requested two hours before the fixed instant, expired one hour before it. */
  const LAPSED = {
    ...BASE_FIELDS,
    approval_id: 'apr-lapsed',
    expires_at: '2026-08-07T11:00:00+00:00',
    requested_at: '2026-08-07T10:00:00+00:00',
    origin: { run_id: 'run-lapsed' },
    run_id: 'run-lapsed',
    state: 'expired',
  };

  /** The same decision, still inside its window. */
  const OPEN = {
    ...BASE_FIELDS,
    approval_id: 'apr-open',
    expires_at: '2026-08-07T13:00:00+00:00',
    requested_at: '2026-08-07T11:39:00+00:00',
    origin: { run_id: 'run-open' },
    run_id: 'run-open',
    state: 'pending',
  };

  function serveLapsed(): void {
    stubReads({
      '/v1/approvals?state=pending': { approvals: [] },
      '/v1/approvals?state=expired': { approvals: [LAPSED] },
      '/v1/approvals?state=decided&limit=10': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
      '/v1/investigations/run-lapsed/interactions': { interactions: [] },
    });
  }

  function serveOpen(): void {
    stubReads({
      '/v1/approvals?state=pending': { approvals: [OPEN] },
      '/v1/approvals?state=expired': { approvals: [] },
      '/v1/approvals?state=decided&limit=10': { approvals: [] },
      '/v1/setup/checklist': { complete: true },
      '/v1/investigations/run-open/interactions': { interactions: [] },
    });
  }

  async function tab(): Promise<void> {
    const { ApprovalsTab } = await import('@/surfaces/screens/approvals');
    const { contextFor, datasetViewer } = await import('../support/dataset');
    render(await ApprovalsTab(contextFor(datasetViewer('populated'))));
  }

  function cardFor(id: string): HTMLElement {
    const found = screen
      .getAllByTestId('decision-card')
      .find((each) => each.getAttribute('data-approval') === id);
    if (found === undefined) throw new Error(`no card for ${id}`);
    return found;
  }

  it('offers no Approve on a card the deployment itself reports as expired', async () => {
    serveLapsed();
    await tab();

    const card = cardFor('apr-lapsed');
    expect(card).toHaveAttribute('data-state', 'expired');

    // The deployment reports the window closed (FR-006's `state=expired`
    // bucket), never a client-side clock comparison. A control that could
    // only fail must not be drawn — addressed by role, since two different
    // components could sit behind this slot depending on the approval.
    expect(within(card).queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(within(card).queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('says why in the place the control was, rather than leaving a gap', async () => {
    serveLapsed();
    await tab();

    // Absence alone reads as a permission the viewer does not hold — this one
    // holds it. The reason is on the card: the window closed, and the honest
    // next step is a fresh reading rather than a decision on a stale one.
    const footer = within(cardFor('apr-lapsed')).getByTestId('expired-footer');
    expect(footer).toHaveTextContent(/window/i);
    expect(within(footer).getByTestId('repropose')).toBeInTheDocument();
    expect(within(footer).getByTestId('discard')).toBeInTheDocument();
  });

  it('still offers Approve on a decision that is inside its window', async () => {
    serveOpen();
    await tab();

    const card = cardFor('apr-open');
    expect(card).toHaveAttribute('data-state', 'pending');
    expect(within(card).getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(within(card).queryByTestId('expired-footer')).toBeNull();
  });
});
