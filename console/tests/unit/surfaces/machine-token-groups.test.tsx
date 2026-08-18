import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MachineTokenGroups, type MachineToken } from '@/surfaces/machine-token-groups';

/**
 * Machine tokens, grouped by purpose — the panel that replaces a flat list of
 * ~15 identical "bootstrap" rows with one group, a count, and a way to reduce
 * it in a single gesture.
 */

const LABELS = {
  purpose: 'What it is for',
  purposeHelp:
    'Issuing another token for a purpose that already has one replaces it — the change is recorded in the audit log.',
  description: 'Individual tokens',
  scopes: 'Scopes',
  issue: 'Issue a token',
  issuing: 'Issuing…',
  shownOnce: 'This is the only time this value is shown. Nothing can read it back.',
  revoke: 'Revoke',
  revoking: 'Revoking…',
  revokeConsequence: 'Clients using this token stop authenticating now.',
  revokeConfirm: 'Revoke it',
  revokeCancel: 'Leave it working',
  revokeOlder: 'Revoke all but the newest',
  revokingOlder: 'Revoking…',
  revokeOlderConsequence:
    'Every older token for this purpose stops authenticating now.',
  revokeOlderConfirm: 'Revoke them',
  revokeOlderCancel: 'Leave them working',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
  none: 'Not recorded',
  lastUsedLabel: 'Last used',
  neverUsed: 'Never used',
  empty: 'No machine tokens have been issued yet.',
};

// The three counted sentences ("N token(s)", "Replaced N earlier token(s)…",
// "N revoked") are no longer part of `labels` — a function is not a value a
// server component may hand a client component, so this panel computes them
// itself from a `locale` prop, against the real catalogue (`en.ts`). Every
// render below passes `locale="en"`, and the assertions that read one of
// these three sentences are checking the shipped English text, not a
// test-only stand-in for it.

function token(
  over: Partial<MachineToken> & { readonly tokenId: string },
): MachineToken {
  return {
    name: 'bootstrap',
    description: '',
    scopes: ['investigation.read', 'token.manage'],
    createdAt: '2026-08-01T00:00:00Z',
    lastUsed: '',
    expires: 'expired',
    revoked: false,
    ...over,
  };
}

let sent: { url: string; method: string; body: unknown }[] = [];

function answerWith(body: unknown, status = 200): void {
  vi.stubGlobal('fetch', (url: unknown, init: RequestInit) => {
    sent.push({
      url: String(url),
      method: String(init.method),
      body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
    });
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  sent = [];
  answerWith({ ok: true, reachable: true, secret: 'nsre-sentinel', superseded: [] });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('grouping by purpose', () => {
  it('collapses many tokens issued for the same purpose into one group with a count', () => {
    const tokens = Array.from({ length: 15 }, (_, index) =>
      token({
        tokenId: `tok-${String(index)}`,
        createdAt: `2026-08-0${String((index % 9) + 1)}T00:00:00Z`,
      }),
    );
    render(
      <MachineTokenGroups
        tokens={tokens}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getAllByTestId('token-group')).toHaveLength(1);
    expect(
      within(screen.getByTestId('token-group')).getByTestId('token-group-count'),
    ).toHaveTextContent('15 tokens');
  });

  it('keeps distinct purposes in distinct groups', () => {
    render(
      <MachineTokenGroups
        tokens={[
          token({ tokenId: 'tok-1', name: 'ci-runner' }),
          token({ tokenId: 'tok-2', name: 'backup-job' }),
        ]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getAllByTestId('token-group')).toHaveLength(2);
  });

  it('shows readable scopes rather than machine slugs', () => {
    render(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1', scopes: ['investigation.read'] })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.queryByText('investigation.read')).toBeNull();
    expect(screen.getByText('Investigation Read')).toBeInTheDocument();
  });

  it('offers only revoked tokens in the collapsed history, and live ones as groups', () => {
    render(
      <MachineTokenGroups
        tokens={[
          token({ tokenId: 'tok-1', name: 'ci-runner', revoked: false }),
          token({ tokenId: 'tok-2', name: 'ci-runner', revoked: true }),
        ]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    // The singular form, not "1 tokens" — the count is exactly one.
    expect(
      within(screen.getByTestId('token-group')).getByTestId('token-group-count'),
    ).toHaveTextContent('1 token');
    expect(screen.getByTestId('revoked-tokens')).toHaveTextContent('1 revoked');
  });
});

describe('revoking all but the newest', () => {
  it('is offered only once a purpose holds more than one live token', () => {
    const { rerender } = render(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1' })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );
    expect(screen.queryByTestId('revoke-older')).toBeNull();

    rerender(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1' }), token({ tokenId: 'tok-2' })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );
    expect(screen.getByTestId('revoke-older')).toBeInTheDocument();
  });

  it('revokes every token but the most recently created one, after confirmation', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[
          token({ tokenId: 'tok-old', createdAt: '2026-07-01T00:00:00Z' }),
          token({ tokenId: 'tok-mid', createdAt: '2026-07-15T00:00:00Z' }),
          token({ tokenId: 'tok-new', createdAt: '2026-08-01T00:00:00Z' }),
        ]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('revoke-older'));
    await user.click(screen.getByTestId('confirm-revoke-older'));

    const call = sent.find((entry) => entry.url.includes('bulk-revoke'));
    expect(call).toBeDefined();
    const body = call?.body as { token_ids: readonly string[] };
    expect(new Set(body.token_ids)).toEqual(new Set(['tok-old', 'tok-mid']));

    // The most recent token stays a group of one; the two older ones are gone.
    // The singular form, not "1 tokens".
    expect(
      within(screen.getByTestId('token-group')).getByTestId('token-group-count'),
    ).toHaveTextContent('1 token');
  });
});

describe('issuing declares and shows the substitution', () => {
  it('names a single replaced token in the singular, not "token(s)"', async () => {
    answerWith({
      ok: true,
      reachable: true,
      secret: 'nsre-sentinel',
      superseded: ['tok-old'],
    });
    const user = userEvent.setup();
    render(
      <MachineTokenGroups tokens={[]} issuedScopes={[]} labels={LABELS} locale="en" />,
    );

    await user.type(screen.getByLabelText(LABELS.purpose), 'ci-runner');
    await user.click(screen.getByTestId('issue-token'));

    const notice = await screen.findByTestId('token-superseded-notice');
    expect(notice).toHaveTextContent(
      'Replaced 1 earlier token issued for the same purpose.',
    );
    expect(notice).not.toHaveTextContent('token(s)');
  });

  it('names several replaced tokens in the plural', async () => {
    answerWith({
      ok: true,
      reachable: true,
      secret: 'nsre-sentinel',
      superseded: ['tok-old', 'tok-mid'],
    });
    const user = userEvent.setup();
    render(
      <MachineTokenGroups tokens={[]} issuedScopes={[]} labels={LABELS} locale="en" />,
    );

    await user.type(screen.getByLabelText(LABELS.purpose), 'ci-runner');
    await user.click(screen.getByTestId('issue-token'));

    expect(await screen.findByTestId('token-superseded-notice')).toHaveTextContent(
      'Replaced 2 earlier tokens issued for the same purpose.',
    );
  });

  it('says nothing was replaced when nothing was', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups tokens={[]} issuedScopes={[]} labels={LABELS} locale="en" />,
    );

    await user.type(screen.getByLabelText(LABELS.purpose), 'ci-runner');
    await user.click(screen.getByTestId('issue-token'));

    await screen.findByTestId('token-secret');
    expect(screen.queryByTestId('token-superseded-notice')).toBeNull();
  });

  it('offers every one of the viewer’s own permissions as a scope to choose, none of them checked', () => {
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['investigation.read', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getByLabelText('Investigation Read')).not.toBeChecked();
    expect(screen.getByLabelText('Token Manage')).not.toBeChecked();
  });

  it('issues only the scopes explicitly checked by hand', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['investigation.read', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText('Investigation Read'));
    await user.type(screen.getByLabelText(LABELS.purpose), 'ci-runner');
    await user.click(screen.getByTestId('issue-token'));

    const call = sent.find((entry) => entry.url.endsWith('/api/token'));
    const body = call?.body as { permissions: readonly string[] };
    expect(body.permissions).toEqual(['investigation.read']);
  });

  it('checking a scope and then unchecking it leaves it out again', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['investigation.read', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText('Investigation Read'));
    await user.click(screen.getByLabelText('Token Manage'));
    await user.click(screen.getByLabelText('Token Manage'));
    await user.type(screen.getByLabelText(LABELS.purpose), 'ci-runner');
    await user.click(screen.getByTestId('issue-token'));

    const call = sent.find((entry) => entry.url.endsWith('/api/token'));
    const body = call?.body as { permissions: readonly string[] };
    expect(body.permissions).toEqual(['investigation.read']);
  });

  it('states the selected-scope count as zero when the form first opens', () => {
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['investigation.read', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getByTestId('scope-selected-count')).toHaveTextContent('0');
  });

  it('updates the selected-scope count as boxes are checked and unchecked', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['investigation.read', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText('Investigation Read'));
    expect(screen.getByTestId('scope-selected-count')).toHaveTextContent('1');

    await user.click(screen.getByLabelText('Investigation Read'));
    expect(screen.getByTestId('scope-selected-count')).toHaveTextContent('0');
  });

  it('reports why an issuance was refused', async () => {
    answerWith(
      { ok: false, reachable: true, reason: 'that name is already a live session' },
      400,
    );
    const user = userEvent.setup();
    render(
      <MachineTokenGroups tokens={[]} issuedScopes={[]} labels={LABELS} locale="en" />,
    );

    await user.type(screen.getByLabelText(LABELS.purpose), 'Console sign-in');
    await user.click(screen.getByTestId('issue-token'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(
      'that name is already a live session',
    );
  });

  it('reports an unreachable deployment as its own message', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new Error('network down')));
    const user = userEvent.setup();
    render(
      <MachineTokenGroups tokens={[]} issuedScopes={[]} labels={LABELS} locale="en" />,
    );

    await user.type(screen.getByLabelText(LABELS.purpose), 'ci-runner');
    await user.click(screen.getByTestId('issue-token'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('a purpose template marks only what it promises', () => {
  it('marks exactly webhook.deliver for the Alert delivery template', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['webhook.deliver', 'investigation.read', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('scope-template-alert-delivery'));

    expect(screen.getByLabelText('Webhook Deliver')).toBeChecked();
    expect(screen.getByLabelText('Investigation Read')).not.toBeChecked();
    expect(screen.getByLabelText('Token Manage')).not.toBeChecked();
  });

  it('marks only read scopes for the Read-only automation template', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['investigation.read', 'config.read', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('scope-template-read-only-automation'));

    expect(screen.getByLabelText('Investigation Read')).toBeChecked();
    expect(screen.getByLabelText('Config Read')).toBeChecked();
    expect(screen.getByLabelText('Token Manage')).not.toBeChecked();
  });

  it('leaves a template’s selection open to being adjusted by hand afterward', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['webhook.deliver', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('scope-template-alert-delivery'));
    await user.click(screen.getByLabelText('Token Manage'));

    expect(screen.getByLabelText('Webhook Deliver')).toBeChecked();
    expect(screen.getByLabelText('Token Manage')).toBeChecked();
  });

  it('replaces rather than adds to a prior manual selection', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['webhook.deliver', 'token.manage']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText('Token Manage'));
    await user.click(screen.getByTestId('scope-template-alert-delivery'));

    expect(screen.getByLabelText('Webhook Deliver')).toBeChecked();
    expect(screen.getByLabelText('Token Manage')).not.toBeChecked();
  });

  it('offers a template disabled, naming why, once its scope is outside the ceiling', () => {
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['investigation.read']}
        labels={LABELS}
        locale="en"
      />,
    );

    const template = screen.getByTestId('scope-template-alert-delivery');
    expect(template).toBeDisabled();
    expect(
      screen.getByTestId('scope-template-alert-delivery-reason'),
    ).not.toHaveTextContent('');
  });
});

describe('scopes render grouped by domain', () => {
  it('renders more than one named group once the offered scopes span more than one domain', () => {
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['investigation.read', 'org.delete', 'identity.write']}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getAllByTestId('scope-group').length).toBeGreaterThan(1);
  });

  it('places every offered scope in exactly one group', () => {
    const issuedScopes = [
      'investigation.read',
      'investigation.run',
      'org.delete',
      'identity.write',
    ];
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={issuedScopes}
        labels={LABELS}
        locale="en"
      />,
    );

    const checkboxCount = screen
      .getAllByTestId('scope-group')
      .reduce(
        (count, group) => count + within(group).getAllByRole('checkbox').length,
        0,
      );
    expect(checkboxCount).toBe(issuedScopes.length);
  });

  it('names each group legibly rather than by its raw domain word', () => {
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['org.delete']}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.queryByText('org')).toBeNull();
    expect(screen.getByText('Org')).toBeInTheDocument();
  });
});

describe('a destructive scope warns before it is issued, and never blocks issuing', () => {
  it('names what Org Delete permits once it is checked, and withdraws the warning once unchecked', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['org.delete', 'investigation.read']}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.queryByTestId('destructive-scope-warning')).toBeNull();

    await user.click(screen.getByLabelText('Org Delete'));
    expect(screen.getByTestId('destructive-scope-warning')).toHaveTextContent(
      'delete the entire organisation',
    );

    await user.click(screen.getByLabelText('Org Delete'));
    expect(screen.queryByTestId('destructive-scope-warning')).toBeNull();
  });

  it('warns for Impersonation Use by its own consequence, not a generic message', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['impersonation.use']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText('Impersonation Use'));
    expect(screen.getByTestId('destructive-scope-warning')).toHaveTextContent(
      'act as any other person',
    );
  });

  it('never disables issuing once a destructive scope is checked', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[]}
        issuedScopes={['owner.assign']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText('Owner Assign'));
    await user.type(screen.getByLabelText(LABELS.purpose), 'break-glass script');

    expect(screen.getByTestId('issue-token')).toBeEnabled();
  });
});

describe('revoking one token', () => {
  it('asks for confirmation, and can be called off', async () => {
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1', name: 'ci-runner' })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(
      within(screen.getByTestId('token-group-detail')).getByTestId('revoke-token'),
    );
    expect(screen.getByTestId('revoke-confirm')).toBeInTheDocument();

    await user.click(screen.getByTestId('cancel-revoke'));
    expect(screen.queryByTestId('revoke-confirm')).toBeNull();
    // Nothing was sent — cancelling asked for nothing.
    expect(sent).toHaveLength(0);
  });

  it('revokes the token once confirmed, and it drops out of the live group', async () => {
    answerWith({ ok: true, reachable: true });
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1', name: 'ci-runner' })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(
      within(screen.getByTestId('token-group-detail')).getByTestId('revoke-token'),
    );
    await user.click(screen.getByTestId('confirm-revoke'));

    expect(
      sent.some((entry) => entry.url.includes('tok-1') && entry.method === 'DELETE'),
    ).toBe(true);
    expect(screen.queryByTestId('token-group')).toBeNull();
    expect(screen.getByTestId('revoked-tokens')).toHaveTextContent('1 revoked');
  });

  it('reports a refusal as the generic failure', async () => {
    answerWith({ ok: false, reachable: true }, 400);
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1', name: 'ci-runner' })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(
      within(screen.getByTestId('token-group-detail')).getByTestId('revoke-token'),
    );
    await user.click(screen.getByTestId('confirm-revoke'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(LABELS.failed);
  });
});

describe('revoking all but the newest fails honestly too', () => {
  it('reports a refusal without silently keeping the group as it was', async () => {
    answerWith({ ok: false, reachable: true }, 400);
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1' }), token({ tokenId: 'tok-2' })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('revoke-older'));
    await user.click(screen.getByTestId('confirm-revoke-older'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(LABELS.failed);
    expect(
      within(screen.getByTestId('token-group')).getByTestId('token-group-count'),
    ).toHaveTextContent('2 tokens');
  });

  it('reports an unreachable deployment as its own message', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new Error('network down')));
    const user = userEvent.setup();
    render(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1' }), token({ tokenId: 'tok-2' })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('revoke-older'));
    await user.click(screen.getByTestId('confirm-revoke-older'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('the group state chip names what the group has done, never a resource health word', () => {
  it('reads "in use" once any of its tokens has a recorded last use, not the raw resource-health word', () => {
    render(
      <MachineTokenGroups
        tokens={[
          token({ tokenId: 'tok-1', name: 'ci-runner', lastUsed: '3 days ago' }),
        ]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    const chip = within(screen.getByTestId('token-group')).getByTestId(
      'token-group-state',
    );
    expect(chip).toHaveTextContent('In use');
    expect(screen.queryByText('healthy', { exact: false })).toBeNull();
    expect(screen.getByTestId('token-group')).not.toHaveTextContent('HEALTHY');
  });

  it('reads "never used" when none of its tokens has a recorded last use', () => {
    render(
      <MachineTokenGroups
        tokens={[token({ tokenId: 'tok-1', name: 'ci-runner', lastUsed: '' })]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    const chip = within(screen.getByTestId('token-group')).getByTestId(
      'token-group-state',
    );
    expect(chip).toHaveTextContent('Never used');
    expect(screen.getByTestId('token-group')).not.toHaveTextContent('HEALTHY');
  });
});

describe('what a group shows about itself', () => {
  it('names the last time any of its tokens were used, when one was', () => {
    render(
      <MachineTokenGroups
        tokens={[
          token({ tokenId: 'tok-1', name: 'ci-runner', lastUsed: '3 days ago' }),
        ]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getByTestId('token-group')).toHaveTextContent('3 days ago');
  });

  it('shows the newest token’s own description when it has one', () => {
    render(
      <MachineTokenGroups
        tokens={[
          token({
            tokenId: 'tok-1',
            name: 'ci-runner',
            description: 'nightly build check',
          }),
        ]}
        issuedScopes={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getByTestId('token-group')).toHaveTextContent('nightly build check');
  });

  it('says nothing has been issued when no live token exists', () => {
    render(
      <MachineTokenGroups tokens={[]} issuedScopes={[]} labels={LABELS} locale="en" />,
    );

    expect(screen.queryAllByTestId('token-group')).toHaveLength(0);
    expect(screen.getByText(LABELS.empty)).toBeInTheDocument();
  });
});
