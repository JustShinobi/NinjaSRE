import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OverrideEditor, type ActiveOverride } from '@/surfaces/override-editor';

/**
 * Widening autonomy for a while, on the record — and taking the widening away.
 *
 * The API refuses a grant with no reason outright, and the control refuses it
 * first: there is no code path here that sends one. Revoking is a click on the
 * override itself — the deployment is the one place that knows whether this
 * node granted it, and every override this node's own bounds report is listed
 * here with a button of its own, never a name typed from memory. Asked to
 * revoke one it did not — an override inherited from above — it answers 404
 * naming where the override has to be revoked instead, and that sentence is
 * rendered exactly as it came back rather than replaced with something this
 * component made up about inheritance.
 */

let sent: { operation: string; payload: unknown }[] = [];

function answerWith(answer: unknown, status = 200, reason = ''): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const body: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    sent.push({
      operation: String(Reflect.get(Object(body), 'operation')),
      payload: Reflect.get(Object(body), 'payload'),
    });
    return Promise.resolve(
      new Response(
        JSON.stringify({ ok: status < 400, reachable: true, reason, answer }),
        {
          status,
          headers: { 'content-type': 'application/json' },
        },
      ),
    );
  });
}

beforeEach(() => {
  sent = [];
  answerWith({ name: 'incident-widen', node_id: 'team-platform' }, 201);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LABELS = {
  grantTitle: 'Grant an override',
  grantName: 'Name',
  grantNameHelp: 'A short identifier for this override, unique on this node.',
  grantLevel: 'Level',
  grantReason: 'Reason',
  grantReasonHelp: 'Recorded in the audit trail beside the override.',
  grantDuration: 'Duration',
  grantDurationDefault: 'Default (2 hours)',
  grantDurationOneHour: '1 hour',
  grantDurationEightHours: '8 hours',
  grantDurationTwentyFourHours: '24 hours',
  grantDurationCustom: 'Custom duration…',
  grantSeconds: 'Seconds (optional)',
  grant: 'Grant',
  granting: 'Granting…',
  granted: 'Granted. It will expire on its own.',
  reasonRequired: 'A reason is required before this can be granted.',
  revokeTitle: 'Revoke an override',
  revokeEmpty: 'No override is active on this node right now.',
  duration: 'Expires',
  reasonLabel: 'Granted because',
  grantedBy: 'Granted by',
  revoke: 'Revoke',
  revoking: 'Revoking…',
  revoked: 'Revoked.',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
};

const LEVELS = ['propose_only', 'act_on_low_risk', 'act_and_report'];

const ONE_ACTIVE: ActiveOverride = {
  name: 'incident-widen',
  level: 'act_and_report',
  expiresIso: '2026-08-13T18:00:00.000Z',
  expiresRelative: 'in 2 hours',
  expiresAbsolute: 'Aug 13, 2026, 6:00 PM UTC',
  reason: 'restoring a paged service',
  grantedBy: 'user-operator',
};

const ACTIVE: readonly ActiveOverride[] = [ONE_ACTIVE];

function editor(active: readonly ActiveOverride[] = []): void {
  render(
    <OverrideEditor
      nodeId="team-platform"
      levels={LEVELS}
      active={active}
      labels={LABELS}
    />,
  );
}

describe('granting an override', () => {
  it('refuses to post a grant with no reason', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');

    expect(screen.getByTestId('grant-override')).toBeDisabled();
    expect(screen.getByTestId('override-reason-required')).toHaveTextContent(
      LABELS.reasonRequired,
    );

    // The disabled control cannot be clicked into firing a request; nothing
    // has reached the wire.
    expect(sent).toHaveLength(0);
  });

  it('says nothing is missing before a name has been typed at all', () => {
    editor();

    expect(screen.queryByTestId('override-reason-required')).toBeNull();
  });

  it('sends the name, level and reason once both are given, and nothing for a duration left at the default', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.selectOptions(screen.getByLabelText('Level'), 'act_and_report');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');

    expect(screen.getByTestId('grant-override')).toBeEnabled();
    await userEvent.click(screen.getByTestId('grant-override'));

    const request = sent.find((each) => each.operation === 'override');
    expect(request?.payload).toMatchObject({
      name: 'incident-widen',
      level: 'act_and_report',
      reason: 'restoring a paged service',
    });
    expect(Reflect.get(Object(request?.payload), 'seconds')).toBeUndefined();
  });

  it('sends the preset’s own seconds once a duration is chosen', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.selectOptions(screen.getByLabelText('Duration'), '8 hours');
    await userEvent.click(screen.getByTestId('grant-override'));

    const request = sent.find((each) => each.operation === 'override');
    expect(Reflect.get(Object(request?.payload), 'seconds')).toBe(8 * 60 * 60);
  });

  it('sends the twenty-four-hour preset at the deployment’s own ceiling', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.selectOptions(screen.getByLabelText('Duration'), '24 hours');
    await userEvent.click(screen.getByTestId('grant-override'));

    const request = sent.find((each) => each.operation === 'override');
    expect(Reflect.get(Object(request?.payload), 'seconds')).toBe(24 * 60 * 60);
  });

  it('reveals a plain seconds field only once a custom duration is chosen', async () => {
    editor();

    expect(screen.queryByLabelText('Seconds (optional)')).toBeNull();

    await userEvent.selectOptions(
      screen.getByLabelText('Duration'),
      'Custom duration…',
    );

    expect(screen.getByLabelText('Seconds (optional)')).toBeInTheDocument();
  });

  it('carries the custom seconds typed once a custom duration is chosen', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.selectOptions(
      screen.getByLabelText('Duration'),
      'Custom duration…',
    );
    await userEvent.type(screen.getByLabelText('Seconds (optional)'), '900');
    await userEvent.click(screen.getByTestId('grant-override'));

    const request = sent.find((each) => each.operation === 'override');
    expect(Reflect.get(Object(request?.payload), 'seconds')).toBe(900);
  });

  it('omits seconds rather than sending a custom one it could not parse', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.selectOptions(
      screen.getByLabelText('Duration'),
      'Custom duration…',
    );
    // A lone minus sign is a valid, incomplete number-field value in the DOM,
    // and `Number('-')` is not finite — the branch a normal keystroke sequence
    // never reaches.
    fireEvent.change(screen.getByLabelText('Seconds (optional)'), {
      target: { value: '-' },
    });
    await userEvent.click(screen.getByTestId('grant-override'));

    const request = sent.find((each) => each.operation === 'override');
    expect(Reflect.get(Object(request?.payload), 'seconds')).toBeUndefined();
  });

  it('names what the identifier is for, before anything is typed', () => {
    editor();

    expect(screen.getByText(LABELS.grantNameHelp)).toBeInTheDocument();
  });

  it('says the reason is recorded in the audit trail', () => {
    editor();

    expect(screen.getByText(LABELS.grantReasonHelp)).toBeInTheDocument();
  });

  it('reports success and clears the form for the next one', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.click(screen.getByTestId('grant-override'));

    expect(await screen.findByTestId('override-granted')).toHaveTextContent(
      LABELS.granted,
    );
    expect(screen.getByLabelText('Name')).toHaveValue('');
    expect(screen.getByLabelText('Reason')).toHaveValue('');
  });

  it('takes the success notice away the moment the form is touched again', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.click(screen.getByTestId('grant-override'));
    await screen.findByTestId('override-granted');

    await userEvent.type(screen.getByLabelText('Name'), 'x');

    expect(screen.queryByTestId('override-granted')).toBeNull();
  });

  it('reports the deployment’s refusal in its own words', async () => {
    editor();
    answerWith({}, 400);

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.click(screen.getByTestId('grant-override'));

    expect(await screen.findByTestId('override-grant-failure')).toHaveTextContent(
      LABELS.failed,
    );
    expect(screen.queryByTestId('override-granted')).toBeNull();
  });

  it('says the deployment could not be reached, which is a different machine to look at', async () => {
    editor();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.click(screen.getByTestId('grant-override'));

    expect(await screen.findByTestId('override-grant-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('revoking an active override', () => {
  it('says there is nothing to revoke when none is active, and offers no name to type', () => {
    editor([]);

    expect(screen.getByTestId('override-revoke-empty')).toHaveTextContent(
      LABELS.revokeEmpty,
    );
    expect(screen.queryByTestId('revoke-override')).toBeNull();
    expect(screen.queryByLabelText('Name of the override')).toBeNull();
  });

  it('lists every active override with its own revoke button, no name to type from memory', () => {
    editor(ACTIVE);

    expect(screen.queryByTestId('override-revoke-empty')).toBeNull();
    expect(screen.queryByLabelText('Name of the override')).toBeNull();
    const row = screen.getByTestId('active-override');
    expect(row).toHaveTextContent('incident-widen');
    expect(row).toHaveTextContent('restoring a paged service');
    expect(row).toHaveTextContent('user-operator');
    expect(screen.getByTestId('revoke-override')).toBeInTheDocument();
  });

  it('names the override the clicked row is for, and nothing else', async () => {
    editor(ACTIVE);

    await userEvent.click(screen.getByTestId('revoke-override'));

    const request = sent.find((each) => each.operation === 'revoke-override');
    expect(request?.payload).toEqual({ name: 'incident-widen' });
  });

  it("names the active override's level in words, when the screen resolved one", () => {
    render(
      <OverrideEditor
        nodeId="team-platform"
        levels={LEVELS}
        levelNames={{
          propose_only: 'Propose only',
          act_on_low_risk: 'Act on low risk',
          act_and_report: 'Act and report',
        }}
        active={ACTIVE}
        labels={LABELS}
      />,
    );

    const chip = screen.getByTestId('active-override-level');
    expect(chip).toHaveTextContent('Act and report');
    expect(chip).not.toHaveTextContent('act_and_report');
  });

  it('falls back to the raw level when the screen resolved no word for it', () => {
    // The levels come from the deployment, not from this console — a level
    // with no resolved name still renders something, never a blank chip.
    render(
      <OverrideEditor
        nodeId="team-platform"
        levels={LEVELS}
        active={ACTIVE}
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('active-override-level')).toHaveTextContent(
      'act_and_report',
    );
  });

  it('reports success and removes the revoked override from its own list', async () => {
    editor(ACTIVE);

    await userEvent.click(screen.getByTestId('revoke-override'));

    expect(await screen.findByTestId('override-revoked')).toHaveTextContent(
      LABELS.revoked,
    );
    expect(screen.queryByTestId('active-override')).toBeNull();
    expect(screen.getByTestId('override-revoke-empty')).toBeInTheDocument();
  });

  it('revokes only the row that was clicked, leaving the others listed', async () => {
    editor([ONE_ACTIVE, { ...ONE_ACTIVE, name: 'incident-widen-2' }]);

    expect(screen.getAllByTestId('active-override')).toHaveLength(2);

    const firstRow = screen.getByText('incident-widen').closest('li');
    if (firstRow === null) throw new Error('expected a row for incident-widen');
    await userEvent.click(within(firstRow).getByTestId('revoke-override'));
    await screen.findByTestId('override-revoked');

    expect(screen.getAllByTestId('active-override')).toHaveLength(1);
    expect(screen.getByText('incident-widen-2')).toBeInTheDocument();
  });

  it('renders the deployment’s own words for an override this node never granted', async () => {
    editor(ACTIVE);
    // The deployment's actual wording for this case, rendered verbatim rather
    // than a sentence this component invented about inheritance.
    answerWith(
      {},
      404,
      'this node granted no override named incident-widen; an inherited override is revoked at the node that granted it',
    );

    await userEvent.click(screen.getByTestId('revoke-override'));

    expect(await screen.findByTestId('override-revoke-failure')).toHaveTextContent(
      'is revoked at the node that granted it',
    );
    // A refusal never removes the row silently: it is still there to retry.
    expect(screen.getByTestId('active-override')).toBeInTheDocument();
  });

  it('says the deployment could not be reached', async () => {
    editor(ACTIVE);
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('revoke-override'));

    expect(await screen.findByTestId('override-revoke-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});
