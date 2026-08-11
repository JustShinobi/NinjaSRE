import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ProposalReview } from '@/surfaces/proposal-review';

/**
 * Deciding one proposal, and the control that does not exist until you have
 * looked.
 *
 * Approving a proposal writes configuration, so the flow never goes straight
 * from a summary to an approval: it asks the deployment what the change would
 * do — the configuration it would resolve to, or what the detector would have
 * found — and only once that answer is on the screen does a control to approve
 * it exist. Rejecting needs none of that and does need a reason, because the
 * reason is what the next proposal of the same thing is read against.
 */

let sent: { operation: string; target: string; verdict: string }[] = [];

const PREVIEW = {
  node_id: 'org-northwind',
  changes: [{ path: 'agents.max_iterations', before: 12, after: 16 }],
};

const DRY_RUN = {
  detector_id: 'corpus-datastore-fill',
  would_fire: true,
  observations: [{ subject: 'datastore-pve02', verdict: 'firing' }],
};

function answerWith(answer: unknown, status = 200): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const body: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    const payload: unknown = Reflect.get(Object(body), 'payload');
    sent.push({
      operation: String(Reflect.get(Object(body), 'operation')),
      target: String(Reflect.get(Object(body), 'target')),
      verdict: String(Reflect.get(Object(payload), 'verdict') ?? ''),
    });
    return Promise.resolve(
      new Response(JSON.stringify(answer), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  sent = [];
  answerWith(PREVIEW);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LABELS = {
  show: 'Show what this would do',
  loading: 'Asking the deployment',
  failed: 'The deployment did not answer.',
  text: 'The text as it would be written',
  preview: 'The configuration this would resolve to',
  dryRun: 'What this detector would have found',
  dryRunQuiet: 'It would have found nothing.',
  approveFirst: 'Approving is available once you have seen what this would do.',
  approve: 'Approve and apply',
  reject: 'Reject',
  reason: 'Why it is being rejected',
  reasonRequired: 'A reason is required to reject.',
};

function renderConfiguration(decidable = true): void {
  render(
    <ProposalReview
      proposalId="prop-0003"
      kind="configuration"
      mechanism="config-preview"
      target="org-northwind"
      payload={{ agents: { max_iterations: 16 } }}
      finalText=""
      decidable={decidable}
      labels={LABELS}
    />,
  );
}

describe('a configuration proposal', () => {
  it('offers no way to approve until the effect has been asked for', () => {
    renderConfiguration();

    expect(screen.queryByTestId('approve')).not.toBeInTheDocument();
    expect(screen.getByTestId('approve-first')).toHaveTextContent(LABELS.approveFirst);
  });

  it('renders the deployment answer rather than a merge of its own', async () => {
    renderConfiguration();

    await userEvent.click(screen.getByTestId('show-effect'));

    expect(screen.getByTestId('effect')).toHaveTextContent('agents.max_iterations');
    expect(screen.getByTestId('effect')).toHaveTextContent('16');
    expect(sent[0]).toMatchObject({ operation: 'preview', target: 'org-northwind' });
  });

  it('offers the approval only once that answer is on the screen', async () => {
    renderConfiguration();

    await userEvent.click(screen.getByTestId('show-effect'));
    await userEvent.click(screen.getByTestId('approve'));

    expect(sent.at(-1)).toMatchObject({
      operation: 'decide',
      target: 'prop-0003',
      verdict: 'approve',
    });
  });

  it('keeps the approval away when the deployment did not answer', async () => {
    answerWith({ reachable: false }, 502);
    renderConfiguration();

    await userEvent.click(screen.getByTestId('show-effect'));

    expect(screen.getByTestId('effect')).toHaveTextContent(LABELS.failed);
    expect(screen.queryByTestId('approve')).not.toBeInTheDocument();
  });

  it('shows nothing to decide with for a viewer who may not decide', () => {
    renderConfiguration(false);

    expect(screen.queryByTestId('approve')).not.toBeInTheDocument();
    expect(screen.queryByTestId('reject')).not.toBeInTheDocument();
    expect(screen.queryByTestId('approve-first')).not.toBeInTheDocument();
  });
});

describe('rejecting', () => {
  it('is unavailable until a reason has been written', async () => {
    renderConfiguration();

    expect(screen.getByTestId('reject')).toBeDisabled();
    await userEvent.type(screen.getByLabelText(LABELS.reason), 'Already covered.');

    expect(screen.getByTestId('reject')).toBeEnabled();
  });

  it('needs no preview, because refusing narrows rather than widens', async () => {
    renderConfiguration();

    await userEvent.type(screen.getByLabelText(LABELS.reason), 'Already covered.');
    await userEvent.click(screen.getByTestId('reject'));

    expect(sent.at(-1)).toMatchObject({ operation: 'decide', verdict: 'reject' });
    expect(sent.some((entry) => entry.operation === 'preview')).toBe(false);
  });
});

describe('a detector proposal', () => {
  it('asks the dry run, and says so when it would have found nothing', async () => {
    answerWith({
      detector_id: 'corpus-datastore-fill',
      would_fire: false,
      observations: [],
    });
    render(
      <ProposalReview
        proposalId="prop-0002"
        kind="detector"
        mechanism="detector-dry-run"
        target="corpus-datastore-fill"
        payload={{ detector_id: 'corpus-datastore-fill' }}
        finalText=""
        decidable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('show-effect'));

    expect(sent[0]).toMatchObject({
      operation: 'detector-dry-run',
      target: 'corpus-datastore-fill',
    });
    expect(screen.getByTestId('effect')).toHaveTextContent(LABELS.dryRunQuiet);
  });

  it('lists what it would have fired on when it would have', async () => {
    answerWith(DRY_RUN);
    render(
      <ProposalReview
        proposalId="prop-0002"
        kind="detector"
        mechanism="detector-dry-run"
        target="corpus-datastore-fill"
        payload={{ detector_id: 'corpus-datastore-fill' }}
        finalText=""
        decidable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('show-effect'));

    expect(screen.getByTestId('effect')).toHaveTextContent('datastore-pve02');
  });
});

describe('an operating-context proposal', () => {
  it('previews the prompt the model would read, from the sections it carries', async () => {
    answerWith({ context: '## Metrics\n\nRead from the host.' });
    render(
      <ProposalReview
        proposalId="prop-0001"
        kind="operating_context"
        mechanism="context-preview"
        target="org-northwind"
        payload={{
          agents: {
            operating_context: { sections: { Metrics: 'Read from the host.' } },
          },
        }}
        finalText=""
        decidable
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('show-effect'));

    expect(screen.getByTestId('effect')).toHaveTextContent('Read from the host.');
    expect(sent[0]).toMatchObject({ operation: 'context-preview' });
  });
});

describe('a knowledge proposal', () => {
  it('needs no round trip, because its effect is its own words', () => {
    render(
      <ProposalReview
        proposalId="prop-0004"
        kind="knowledge"
        mechanism="text"
        target="proposed-prop-0004"
        payload={{}}
        finalText="Compare the memory limit against the previous revision."
        decidable
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('effect')).toHaveTextContent('previous revision');
    expect(screen.getByTestId('approve')).toBeInTheDocument();
  });
});
