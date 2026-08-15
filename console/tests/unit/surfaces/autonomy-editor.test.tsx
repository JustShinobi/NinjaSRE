import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  AutonomyEditor,
  type EditableBound,
  type EditableRule,
} from '@/surfaces/autonomy-editor';

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
  newRuleTitle: 'Create a rule',
  newRuleScope: 'New rule scope',
  newRuleLevel: 'New rule level',
  newRuleTeam: 'Team',
  newRuleResourceKind: 'Resource kind',
  newRuleResourceId: 'New rule resource',
  newRuleCapability: 'New rule capability',
  newRuleLabelName: 'Label name',
  newRuleLabelValue: 'Label value',
  addRule: 'Add rule',
  freezesTitle: 'Freeze windows',
  freezeName: 'Freeze name',
  freezeStart: 'Starts',
  freezeEnd: 'Ends',
  freezeReason: 'Reason',
  addFreeze: 'Add freeze',
  budgetsTitle: 'Budgets',
  budgetName: 'Budget name',
  budgetLimit: 'Limit',
  budgetCountedBy: 'Counted by',
  addBudget: 'Add budget',
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

describe('creating a rule with a scope, rather than only levelling an existing one', () => {
  it('adds a deployment-wide row when no scope narrower than that is chosen', async () => {
    editor();

    await userEvent.selectOptions(
      screen.getByLabelText('New rule level'),
      'act_and_report',
    );
    await userEvent.click(screen.getByTestId('add-rule'));

    const added = screen.getAllByTestId('rule-editor');
    expect(added).toHaveLength(2);
  });

  it('scopes the new rule to one capability when that kind is chosen', async () => {
    editor();

    await userEvent.selectOptions(
      screen.getByLabelText('New rule scope'),
      'capability',
    );
    await userEvent.type(
      screen.getByLabelText('New rule capability'),
      'estate.enable_backup_job',
    );
    await userEvent.click(screen.getByTestId('add-rule'));
    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));

    const previewed = sent.find((each) => each.operation === 'preview')?.payload;
    const rules: unknown = Reflect.get(Object(previewed), 'rules');
    const added = (rules as readonly unknown[]).find(
      (rule) =>
        Reflect.get(Object(Reflect.get(Object(rule), 'scope')), 'kind') ===
        'capability',
    );
    expect(Reflect.get(Object(Reflect.get(Object(added), 'scope')), 'capability')).toBe(
      'estate.enable_backup_job',
    );
  });

  it('shows the matching field for every other scope kind, and none of the fields no kind needs', async () => {
    editor();
    const scope = screen.getByLabelText('New rule scope');

    await userEvent.selectOptions(scope, 'team');
    expect(screen.getByLabelText('Team')).toBeInTheDocument();
    expect(screen.queryByLabelText('New rule resource')).not.toBeInTheDocument();

    await userEvent.selectOptions(scope, 'resource_kind');
    expect(screen.getByLabelText('Resource kind')).toBeInTheDocument();
    expect(screen.queryByLabelText('Team')).not.toBeInTheDocument();

    await userEvent.selectOptions(scope, 'labels');
    expect(screen.getByLabelText('Label name')).toBeInTheDocument();
    expect(screen.getByLabelText('Label value')).toBeInTheDocument();

    await userEvent.selectOptions(scope, 'resource');
    expect(screen.getByLabelText('New rule resource')).toBeInTheDocument();
    expect(screen.queryByLabelText('New rule capability')).not.toBeInTheDocument();

    await userEvent.selectOptions(scope, 'capability_resource');
    expect(screen.getByLabelText('New rule capability')).toBeInTheDocument();
    expect(screen.getByLabelText('New rule resource')).toBeInTheDocument();
  });

  it('scopes a new rule to one team, one resource kind, and a label pair, each carried into the saved document', async () => {
    editor();

    await userEvent.selectOptions(screen.getByLabelText('New rule scope'), 'team');
    await userEvent.type(screen.getByLabelText('Team'), 'team-payments');
    await userEvent.click(screen.getByTestId('add-rule'));

    await userEvent.selectOptions(screen.getByLabelText('New rule scope'), 'resource');
    await userEvent.type(screen.getByLabelText('New rule resource'), 'vm-201');
    await userEvent.click(screen.getByTestId('add-rule'));

    await userEvent.selectOptions(screen.getByLabelText('New rule scope'), 'labels');
    await userEvent.type(screen.getByLabelText('Label name'), 'tier');
    await userEvent.type(screen.getByLabelText('Label value'), 'critical');
    await userEvent.click(screen.getByTestId('add-rule'));

    await userEvent.selectOptions(
      screen.getByLabelText('New rule scope'),
      'capability_resource',
    );
    await userEvent.type(
      screen.getByLabelText('New rule capability'),
      'estate.restart',
    );
    await userEvent.type(screen.getByLabelText('New rule resource'), 'vm-9');
    await userEvent.click(screen.getByTestId('add-rule'));

    expect(screen.getAllByTestId('rule-editor')).toHaveLength(5);

    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));
    const previewed = sent.find((each) => each.operation === 'preview')?.payload;
    const rules = Reflect.get(Object(previewed), 'rules') as readonly unknown[];
    const kinds = rules.map((rule): unknown =>
      Reflect.get(Object(Reflect.get(Object(rule), 'scope')), 'kind'),
    );
    expect(kinds).toEqual(
      expect.arrayContaining(['team', 'resource', 'labels', 'capability_resource']),
    );
    const labelled = rules.find(
      (rule) =>
        Reflect.get(Object(Reflect.get(Object(rule), 'scope')), 'kind') === 'labels',
    );
    expect(
      Reflect.get(Object(Reflect.get(Object(labelled), 'scope')), 'labels'),
    ).toEqual([{ name: 'tier', value: 'critical' }]);
  });
});

describe('freezes and budgets, carried through and created', () => {
  const FREEZES: readonly EditableBound[] = [
    {
      name: 'nightly-backups',
      record: { name: 'nightly-backups', start: '01:00', end: '04:00' },
    },
  ];

  it('carries an existing freeze through a save that only changed a rule level, rather than wiping it', async () => {
    render(
      <AutonomyEditor
        nodeId="team-platform"
        rules={RULES}
        levels={LEVELS}
        dryRun={false}
        freezes={FREEZES}
        labels={LABELS}
      />,
    );
    await raiseTheLevel();
    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));
    await userEvent.click(await screen.findByTestId('save-autonomy'));

    const written = sent.find((each) => each.operation === 'save')?.payload;
    const freezes: unknown = Reflect.get(Object(written), 'freezes');
    expect(freezes).toEqual([FREEZES[0]?.record]);
  });

  it('adds a new freeze window to the document a save carries', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Freeze name'), 'nightly-backups');
    await userEvent.type(screen.getByLabelText('Starts'), '01:00');
    await userEvent.type(screen.getByLabelText('Ends'), '04:00');
    await userEvent.click(screen.getByTestId('add-freeze'));
    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));

    const previewed = sent.find((each) => each.operation === 'preview')?.payload;
    const freezes = Reflect.get(Object(previewed), 'freezes') as readonly unknown[];
    const names = freezes.map((each): unknown => Reflect.get(Object(each), 'name'));
    expect(names).toContain('nightly-backups');
  });

  it('adds a new budget to the document a save carries', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Budget name'), 'restart-cap');
    await userEvent.type(screen.getByLabelText('Limit'), '5');
    await userEvent.click(screen.getByTestId('add-budget'));
    await userEvent.click(screen.getByTestId('ask-autonomy-preview'));

    const previewed = sent.find((each) => each.operation === 'preview')?.payload;
    const budgets = Reflect.get(Object(previewed), 'budgets') as readonly unknown[];
    const names = budgets.map((each): unknown => Reflect.get(Object(each), 'name'));
    expect(names).toContain('restart-cap');
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
