import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AutonomyEditor, type EditableRule } from '@/surfaces/autonomy-editor';

/**
 * Changing what can happen without a person, and the order it has to be read in.
 *
 * The save is below the newly-autonomous list rather than beside the form, and
 * it does not exist until a preview of the *current* posture has come back.
 * That ordering is the control: a confirmation dialogue asks a question with no
 * evidence in front of it, and the evidence here is a replay of the
 * deployment's own recorded actions under both policies.
 *
 * Nothing in this component resolves anything. Which rule wins, what a level
 * means, what an action would do — all of it is the deployment's answer,
 * rendered.
 */

let sent: { operation: string; payload: unknown }[] = [];

const PREVIEW = {
  summary: 'Two of forty-one actions would be decided differently.',
  considered: 41,
  changed: 2,
  newly_autonomous: 1,
  actions: [
    {
      action_id: 'act-1',
      capability: 'estate.enable_backup_job',
      before: 'propose_only',
      after: 'act_and_report',
      after_reason: 'the capability rule now covers it',
      more_autonomous: true,
    },
    {
      action_id: 'act-2',
      capability: 'estate.unlock_guest',
      before: 'act_and_report',
      after: 'propose_only',
      after_reason: 'the deployment rule is narrower now',
      more_autonomous: false,
    },
  ],
};

const EXPLANATION = {
  decision: 'propose',
  level: 'propose_only',
  reason: 'no rule raises this capability above proposing',
  winning_rule: 'deployment',
};

function answerWith(answer: unknown, status = 200): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const body: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    sent.push({
      operation: String(Reflect.get(Object(body), 'operation')),
      payload: Reflect.get(Object(body), 'payload'),
    });
    return Promise.resolve(
      new Response(JSON.stringify({ ok: status < 400, reachable: true, answer }), {
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
  level: 'Level',
  preview: 'What would this decide differently?',
  previewing: 'Asking…',
  explain: 'Explain',
  explaining: 'Explaining…',
  explainCapability: 'Capability',
  explainResource: 'Resource',
  save: 'Save this posture',
  saving: 'Saving…',
  saved: 'Saved.',
  failed: 'The deployment refused this posture.',
  unreachable: 'The deployment could not be reached.',
  previewFirst: 'See what this would have decided differently before saving it.',
  considered: 'Considered',
  changed: 'Changed',
  newlyAutonomous: 'Newly autonomous',
  nothingChanges: 'Nothing would become more autonomous.',
  dryRunOn: 'Simulate everything',
  dryRunOff: 'Stop simulating',
  dryRunBanner: 'Simulating: every action is decided and none of them is performed.',
  decision: 'Decision',
  winningRule: 'Winning rule',
};

const RULES: readonly EditableRule[] = [
  {
    ruleId: 'deployment',
    scope: 'deployment',
    matcher: '—',
    level: 'propose_only',
    riskBound: 'low',
    record: { scope: { kind: 'deployment' }, level: 'propose_only', risk_bound: 'low' },
  },
];

const LEVELS = ['propose_only', 'act_on_low_risk', 'act_and_report'];

function editor(dryRun = false): void {
  render(
    <AutonomyEditor
      nodeId="team-platform"
      rules={RULES}
      levels={LEVELS}
      dryRun={dryRun}
      labels={LABELS}
    />,
  );
}

async function raiseTheLevel(): Promise<void> {
  await userEvent.selectOptions(screen.getByLabelText('Level'), 'act_and_report');
}

describe('the two answers that come before the save', () => {
  it('has no save control until the posture has been previewed', async () => {
    editor();
    await raiseTheLevel();

    expect(screen.queryByTestId('save-autonomy')).toBeNull();
    expect(screen.getByTestId('autonomy-preview-first')).toHaveTextContent(
      LABELS.previewFirst,
    );
  });

  it('shows the newly-autonomous list, and puts the save below it', async () => {
    editor();
    await raiseTheLevel();
    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));

    const list = await screen.findAllByTestId('newly-autonomous');
    // Only the actions that became *more* autonomous. The other half of the
    // diff is reassurance; this is the half somebody has to have read.
    expect(list).toHaveLength(1);
    expect(list[0]).toHaveAttribute('data-capability', 'estate.enable_backup_job');

    const preview = screen.getByTestId('autonomy-preview');
    expect(preview).toContainElement(screen.getByTestId('save-autonomy'));
  });

  it('reports the counts the deployment computed rather than counting rows', async () => {
    editor();
    await raiseTheLevel();
    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));

    const preview = await screen.findByTestId('autonomy-preview');
    expect(preview).toHaveTextContent('41');
    expect(preview).toHaveTextContent(PREVIEW.summary);
  });

  it('takes the save away again the moment the posture changes', async () => {
    editor();
    await raiseTheLevel();
    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));
    expect(await screen.findByTestId('save-autonomy')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Level'), 'act_on_low_risk');

    expect(screen.queryByTestId('save-autonomy')).toBeNull();
  });

  it('saves exactly the document that was previewed', async () => {
    editor();
    await raiseTheLevel();
    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));
    await userEvent.click(await screen.findByTestId('save-autonomy'));

    const previewed = sent.find((each) => each.operation === 'preview')?.payload;
    const written = sent.find((each) => each.operation === 'save')?.payload;
    expect(written).toEqual(previewed);
  });

  it('explains one action, naming the rule that wins and why', async () => {
    editor();
    answerWith(EXPLANATION);

    await userEvent.type(screen.getByLabelText('Capability'), 'estate.unlock_guest');
    await userEvent.type(screen.getByLabelText('Resource'), 'vm-201');
    await userEvent.click(screen.getByTestId('ask-explain'));

    const explained = await screen.findByTestId('explanation');
    expect(explained).toHaveTextContent('deployment');
    expect(explained).toHaveTextContent('no rule raises this capability');
  });

  it('will not explain an action nobody has named', () => {
    editor();

    expect(screen.getByTestId('ask-explain')).toBeDisabled();
  });
});

describe('the dry-run boundary', () => {
  it('says nothing while the deployment is really acting', () => {
    editor(false);

    expect(screen.queryByTestId('dry-run-banner')).toBeNull();
  });

  it('carries a persistent banner while it is simulating', () => {
    editor(true);

    const banner = screen.getByTestId('dry-run-banner');
    expect(banner).toHaveTextContent('none of them is performed');
    // A state colour, never the accent: the accent is what the console uses for
    // "press this", and this is a statement rather than a control.
    expect(banner.className).toContain('warning');
    expect(banner.className).not.toContain('accent');
  });

  it('turns simulation on through the deployment and then shows the banner', async () => {
    answerWith({ node_id: 'team-platform', dry_run: true });
    editor(false);

    await userEvent.click(screen.getByTestId('toggle-dry-run'));

    expect(sent.at(-1)?.operation).toBe('dry-run');
    expect(await screen.findByTestId('dry-run-banner')).toBeInTheDocument();
  });
});

describe('when the deployment will not have it', () => {
  it('reports the refusal in the deployment’s own words', async () => {
    editor();
    await raiseTheLevel();
    answerWith({}, 400);

    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));

    expect(await screen.findByTestId('autonomy-failure')).toHaveTextContent(
      LABELS.failed,
    );
    expect(screen.queryByTestId('save-autonomy')).toBeNull();
  });

  it('says it could not be reached, which is a different machine to look at', async () => {
    editor();
    await raiseTheLevel();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));

    expect(await screen.findByTestId('autonomy-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});
