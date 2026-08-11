import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OverrideEditor } from '@/surfaces/override-editor';

/**
 * Widening autonomy for a while, on the record — and taking the widening away.
 *
 * The API refuses a grant with no reason outright, and the control refuses it
 * first: there is no code path here that sends one. Revoking takes only a name,
 * because the deployment is the one place that knows whether this node granted
 * it — asked for one it did not, it answers 404 naming where the override has
 * to be revoked instead, and that sentence is rendered exactly as it came back
 * rather than replaced with something this component made up about inheritance.
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
  grantLevel: 'Level',
  grantReason: 'Reason',
  grantSeconds: 'Seconds (optional)',
  grant: 'Grant',
  granting: 'Granting…',
  granted: 'Granted. It will expire on its own.',
  reasonRequired: 'A reason is required before this can be granted.',
  revokeTitle: 'Revoke an override',
  revokeName: 'Name of the override',
  revoke: 'Revoke',
  revoking: 'Revoking…',
  revoked: 'Revoked.',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
};

const LEVELS = ['propose_only', 'act_on_low_risk', 'act_and_report'];

function editor(): void {
  render(<OverrideEditor nodeId="team-platform" levels={LEVELS} labels={LABELS} />);
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

  it('sends the name, level and reason once both are given', async () => {
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

  it('carries seconds when a duration was given', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
    await userEvent.type(screen.getByLabelText('Seconds (optional)'), '900');
    await userEvent.click(screen.getByTestId('grant-override'));

    const request = sent.find((each) => each.operation === 'override');
    expect(Reflect.get(Object(request?.payload), 'seconds')).toBe(900);
  });

  it('omits seconds rather than sending one it could not parse', async () => {
    editor();

    await userEvent.type(screen.getByLabelText('Name'), 'incident-widen');
    await userEvent.type(screen.getByLabelText('Reason'), 'restoring a paged service');
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

describe('revoking an override', () => {
  it('will not revoke until an override has been named', () => {
    editor();

    expect(screen.getByTestId('revoke-override')).toBeDisabled();
  });

  it('names the override in the request, and nothing else', async () => {
    editor();

    await userEvent.type(
      screen.getByLabelText('Name of the override'),
      'incident-widen',
    );
    await userEvent.click(screen.getByTestId('revoke-override'));

    const request = sent.find((each) => each.operation === 'revoke-override');
    expect(request?.payload).toEqual({ name: 'incident-widen' });
  });

  it('reports success, and clears the name for the next one', async () => {
    editor();

    await userEvent.type(
      screen.getByLabelText('Name of the override'),
      'incident-widen',
    );
    await userEvent.click(screen.getByTestId('revoke-override'));

    expect(await screen.findByTestId('override-revoked')).toHaveTextContent(
      LABELS.revoked,
    );
    expect(screen.getByLabelText('Name of the override')).toHaveValue('');
  });

  it('renders the deployment’s own words for an override this node never granted', async () => {
    editor();
    // The deployment's actual wording for this case, rendered verbatim rather
    // than a sentence this component invented about inheritance.
    answerWith(
      {},
      404,
      'this node granted no override named incident-widen; an inherited override is revoked at the node that granted it',
    );

    await userEvent.type(
      screen.getByLabelText('Name of the override'),
      'incident-widen',
    );
    await userEvent.click(screen.getByTestId('revoke-override'));

    expect(await screen.findByTestId('override-revoke-failure')).toHaveTextContent(
      'is revoked at the node that granted it',
    );
  });

  it('says the deployment could not be reached', async () => {
    editor();
    await userEvent.type(
      screen.getByLabelText('Name of the override'),
      'incident-widen',
    );
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('revoke-override'));

    expect(await screen.findByTestId('override-revoke-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});
