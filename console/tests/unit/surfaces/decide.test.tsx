import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DecisionControls } from '@/surfaces/decision';
import { ConfigPreview } from '@/surfaces/preview';
import { CredentialField } from '@/surfaces/credential';
import { Figure } from '@/surfaces/figure';
import { ProposalCard, PROPOSAL_FIELDS } from '@/surfaces/proposal';
import { DependencyGraph, NEIGHBOUR_BOUND } from '@/surfaces/graph';
import { AttentionBlock } from '@/surfaces/attention';
import { ActivityFeed } from '@/surfaces/activity';

/**
 * The pieces a screen is assembled from, each against the property it exists to
 * hold.
 *
 * Every one of these is a rule that is easy to state and easy to lose: eight
 * fields in an order, a figure that cannot be drawn without a drill-down, a
 * rejection that cannot be sent without a reason, a credential field that has no
 * way to show what is stored.
 */

let sent: { url: string; init: RequestInit } | null = null;

beforeEach(() => {
  sent = null;
  vi.stubGlobal('fetch', (url: unknown, init: RequestInit) => {
    sent = { url: String(url), init };
    return Promise.resolve(
      new Response(
        JSON.stringify({
          changes: [{ path: 'investigation.max_loops', before: 8, after: 12 }],
          locked: { 'approval.required_above': 'org' },
          approval_gated: ['approval.required_above'],
          requires_approval: true,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** What was actually put on the wire, as text. */
function bodySent(): string {
  const body = sent?.init.body;
  return typeof body === 'string' ? body : '';
}

describe('the proposal card', () => {
  const ROWS = PROPOSAL_FIELDS.map((field) => ({
    field,
    label: field,
    value: `what ${field} says`,
  }));

  it('carries all eight documented fields, in the documented order', () => {
    render(<ProposalCard heading="Proposed action" risk="Risk 4 of 5" rows={ROWS} />);

    const drawn = screen
      .getAllByTestId('proposal-row')
      .map((row) => row.getAttribute('data-field'));
    expect(drawn).toEqual([...PROPOSAL_FIELDS]);
  });

  it('shows the decision controls only when it is handed them', () => {
    const { rerender } = render(
      <ProposalCard heading="Proposed action" risk="Risk 4 of 5" rows={ROWS} />,
    );
    expect(screen.queryByTestId('decision')).toBeNull();

    rerender(
      <ProposalCard
        heading="Proposed action"
        risk="Risk 4 of 5"
        rows={ROWS}
        decision={<span data-testid="decision">here</span>}
      />,
    );
    expect(screen.getByTestId('decision')).toBeInTheDocument();
  });

  it('draws what each item protects as its own list', () => {
    render(
      <ProposalCard
        heading="Proposed action"
        risk="Risk 4 of 5"
        rows={[
          {
            field: 'protects',
            label: 'What each protects',
            value: '',
            items: [{ badge: 'safe', text: 'vm-9098-disk-0 — orphaned volume' }],
          },
        ]}
      />,
    );

    expect(screen.getByText(/vm-9098-disk-0/)).toBeInTheDocument();
  });
});

describe('deciding in place', () => {
  const LABELS = {
    approve: 'Approve',
    reject: 'Reject',
    reason: 'Why it is being rejected',
    reasonRequired: 'A reason is required to reject.',
  };

  it('will not send a rejection until a reason is written', async () => {
    render(<DecisionControls interactionId="int-1" labels={LABELS} />);

    expect(screen.getByTestId('reject')).toBeDisabled();
    expect(screen.getByText(LABELS.reasonRequired)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(LABELS.reason), 'no rollback exists');
    expect(screen.getByTestId('reject')).toBeEnabled();
  });

  it('approves without one, because an approval is not a refusal', async () => {
    render(<DecisionControls interactionId="int-1" labels={LABELS} />);

    await userEvent.click(screen.getByTestId('approve'));

    expect(sent?.url).toBe('/api/decision');
    expect(bodySent()).toContain('"verdict":"approve"');
  });

  it('sends the reason with a rejection', async () => {
    render(<DecisionControls interactionId="int-1" labels={LABELS} />);

    await userEvent.type(screen.getByLabelText(LABELS.reason), 'no rollback exists');
    await userEvent.click(screen.getByTestId('reject'));

    expect(bodySent()).toContain('no rollback exists');
  });
});

describe('previewing a change', () => {
  const LABELS = {
    setting: 'Setting',
    value: 'Value',
    submit: 'Preview',
    before: 'Now',
    after: 'After saving',
    locked: 'Locked here',
    lockedDetail: 'A change made here would be refused.',
    gated: 'Approval-gated',
    gatedDetail: 'Saving this queues a change rather than applying it.',
    provenance: 'Set at',
    empty: 'Nothing would change',
  };

  it('renders the deployment’s answer rather than working one out', async () => {
    render(
      <ConfigPreview
        nodeId="org-northwind"
        settings={[{ name: 'investigation.max_loops', value: '8' }]}
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('ask-preview'));

    const change = await screen.findByTestId('preview-change');
    expect(change).toHaveAttribute('data-path', 'investigation.max_loops');
    expect(change).toHaveTextContent('8');
    expect(change).toHaveTextContent('12');
    expect(sent?.url).toBe('/api/preview');
  });

  it('says what a locked value would do, and that a gated one is queued', async () => {
    render(
      <ConfigPreview
        nodeId="org-northwind"
        settings={[{ name: 'investigation.max_loops', value: '8' }]}
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('ask-preview'));

    expect(await screen.findByTestId('locked')).toHaveTextContent(LABELS.lockedDetail);
    expect(screen.getByTestId('gated')).toHaveTextContent(LABELS.gatedDetail);
  });

  it('shows nothing about a change nobody has asked about yet', () => {
    render(<ConfigPreview nodeId="n" settings={[]} labels={LABELS} />);

    expect(screen.queryByTestId('preview-changes')).toBeNull();
  });
});

describe('a credential field', () => {
  const LABELS = {
    title: 'Credentials',
    replace: 'Replace this credential',
    stored: 'A credential is stored. It is never shown again.',
    absent: 'No credential is stored.',
    verify: 'Verify now',
  };

  it('posts to the API origin rather than to this one', () => {
    render(
      <CredentialField
        integration="proxmox"
        required={['api_token']}
        labels={LABELS}
      />,
    );

    const form = screen.getByTestId('credential');
    // `apiOrigin()` is empty in a test, so what is asserted is the path — and
    // that it is the deployment's rather than one of this console's own routes.
    expect(form.getAttribute('action')).toBe('/v1/integrations/proxmox/verify');
    expect(form.getAttribute('action')).not.toContain('/api/');
  });

  it('never renders a stored secret back, and hides what is typed', () => {
    render(
      <CredentialField
        integration="proxmox"
        required={['api_token']}
        labels={LABELS}
      />,
    );

    const field = screen.getByLabelText('api_token');
    expect(field).toHaveValue('');
    expect(field).toHaveAttribute('type', 'password');
    expect(screen.getByText(LABELS.stored)).toBeInTheDocument();
  });

  it('says so when there is nothing stored', () => {
    render(<CredentialField integration="proxmox" required={[]} labels={LABELS} />);

    expect(screen.getByText(LABELS.absent)).toBeInTheDocument();
  });
});

describe('a summary figure', () => {
  it('cannot be rendered without a drill-down', () => {
    expect(() =>
      render(
        <Figure
          label="Resources watched"
          value="92"
          context="2 nodes · 84 guests"
          href="  "
          drillLabel="See the list"
        />,
      ),
    ).toThrow(/drill-down/i);
  });

  it('links the figure to the list it counts', () => {
    render(
      <Figure
        label="Resources watched"
        value="92"
        context="2 nodes · 84 guests"
        href="/resources"
        drillLabel="See the list behind this figure"
      />,
    );

    expect(screen.getByTestId('figure')).toHaveAttribute('href', '/resources');
    expect(screen.getByText('2 nodes · 84 guests')).toBeInTheDocument();
  });
});

describe('the graph and the list beside it', () => {
  function neighbours(
    count: number,
  ): { id: string; name: string; kind: string; href: string }[] {
    return Array.from({ length: count }, (_, index) => ({
      id: `n-${String(index)}`,
      name: `service ${String(index)}`,
      kind: 'service',
      href: `/topology?node=n-${String(index)}`,
    }));
  }

  it('bounds what it draws, however many dependents there are', () => {
    render(
      <DependencyGraph
        subject={{ id: 'subject', name: 'local-lvm', kind: 'datastore', href: '#' }}
        dependencies={neighbours(3)}
        dependents={neighbours(200)}
        labels={{
          title: 'Neighbourhood',
          dependencies: 'Depends on',
          dependents: 'Dependents',
        }}
      />,
    );

    // Two hundred boxes is a picture nobody can read. The screen's list has all
    // of them; this is the readable half.
    expect(screen.getAllByTestId('graph-node')).toHaveLength(3 + NEIGHBOUR_BOUND);
    expect(screen.getByTestId('graph-subject')).toHaveTextContent('local-lvm');
  });

  it('is a named picture rather than an unlabelled drawing', () => {
    render(
      <DependencyGraph
        subject={{ id: 'subject', name: 'local-lvm', kind: 'datastore', href: '#' }}
        dependencies={[]}
        dependents={[]}
        labels={{
          title: 'Neighbourhood',
          dependencies: 'Depends on',
          dependents: 'Dependents',
        }}
      />,
    );

    expect(screen.getByRole('img', { name: 'Neighbourhood' })).toBeInTheDocument();
  });
});

describe('the attention block and the activity feed', () => {
  it('is absent when nothing is waiting, rather than cheerfully empty', () => {
    const { container } = render(
      <AttentionBlock
        heading="0 items need you"
        oldest=""
        rows={[]}
        openLabel="Open"
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('reaches each subject in one click', () => {
    render(
      <AttentionBlock
        heading="1 item needs you"
        oldest="Oldest 2h 14m"
        rows={[
          {
            id: 'a-1',
            kind: 'approval',
            title: 'Reclaim 41 GiB on local-lvm',
            detail: 'awaiting decision',
            href: '/approvals?selected=a-1',
            since: '2h ago',
          },
        ]}
        openLabel="Open"
      />,
    );

    expect(screen.getByRole('link')).toHaveAttribute('href', '/approvals?selected=a-1');
    expect(screen.getByTestId('attention-row')).toHaveAttribute(
      'data-kind',
      'approval',
    );
  });

  it('gives every activity entry a kind in words and an absolute instant', () => {
    render(
      <ActivityFeed
        entries={[
          {
            id: 'e-1',
            kind: 'incident',
            kindLabel: 'Incidents',
            outcome: 'danger',
            title: 'Quorum margin is zero',
            detail: 'pve.quorum.margin',
            href: '/incidents/INC-1',
            relative: '4 minutes ago',
            absolute: '7 Aug 2026, 21:36:00',
            iso: '2026-08-07T21:36:00.000Z',
          },
        ]}
      />,
    );

    expect(screen.getByTestId('activity-kind')).toHaveTextContent('Incidents');
    // On hover *and* on focus: a tooltip a pointer alone can reach is a tooltip
    // half the operators cannot.
    const when = screen.getByText('4 minutes ago');
    expect(when).toHaveAttribute('title', '7 Aug 2026, 21:36:00');
    expect(when).toHaveAttribute('datetime', '2026-08-07T21:36:00.000Z');
  });
});
