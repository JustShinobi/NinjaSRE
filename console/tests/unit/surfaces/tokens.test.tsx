import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TokenPanel, type IssuedToken } from '@/surfaces/tokens';

/**
 * A machine token: shown once, and revoked with the consequence named.
 *
 * "Once" is not a policy this component keeps — it is the only thing that can
 * happen. The deployment stores a hash and no route returns a secret, so the
 * value exists in React state and nowhere else, and the assertions below are
 * about the *document*: after a re-render, after another issue, after a change
 * of mind, the secret is not in it.
 */

const SENTINEL = 'nsre-token-0000-sentinel';

let sent: { url: string; method: string }[] = [];

function answerWith(body: unknown, status = 200): void {
  vi.stubGlobal('fetch', (url: unknown, init: RequestInit) => {
    sent.push({ url: String(url), method: String(init.method) });
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
  answerWith({ ok: true, reachable: true, secret: SENTINEL });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LABELS = {
  name: 'What it is for',
  issue: 'Issue a token',
  issuing: 'Issuing…',
  shownOnce: 'This is the only time this value is shown. Nothing can read it back.',
  revoke: 'Revoke',
  revoking: 'Revoking…',
  revoked: 'Revoked',
  revokeConsequence: 'Clients using this token stop authenticating now.',
  revokeConfirm: 'Revoke it',
  revokeCancel: 'Leave it working',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
  none: 'Not recorded',
  revokedGroup: '{count} revoked',
};

const TOKENS: readonly IssuedToken[] = [
  {
    tokenId: 'tok-1',
    name: 'nightly-backup-checker',
    scopes: ['investigation.read'],
    revoked: false,
    expires: 'in 300 days',
  },
];

function panel(tokens: readonly IssuedToken[] = TOKENS): void {
  render(<TokenPanel tokens={tokens} labels={LABELS} />);
}

describe('issuing one', () => {
  it('will not issue a token nobody has said what it is for', () => {
    panel();

    expect(screen.getByTestId('issue-token')).toBeDisabled();
  });

  it('shows the secret exactly once, and says that is what happened', async () => {
    panel();

    await userEvent.type(screen.getByLabelText(LABELS.name), 'ci-runner');
    await userEvent.click(screen.getByTestId('issue-token'));

    expect(await screen.findByTestId('token-secret')).toHaveTextContent(SENTINEL);
    expect(screen.getByText(LABELS.shownOnce)).toBeInTheDocument();
  });

  it('sends the value in nothing at all — it only ever comes back', async () => {
    panel();

    await userEvent.type(screen.getByLabelText(LABELS.name), 'ci-runner');
    await userEvent.click(screen.getByTestId('issue-token'));

    expect(sent.at(-1)?.url).toBe('/api/token');
    expect(sent.at(-1)?.url).not.toContain(SENTINEL);
  });

  it('takes the secret out of the document the moment the next one is named', async () => {
    panel();

    await userEvent.type(screen.getByLabelText(LABELS.name), 'ci-runner');
    await userEvent.click(screen.getByTestId('issue-token'));
    await screen.findByTestId('token-secret');

    await userEvent.type(screen.getByLabelText(LABELS.name), 'a');

    // Not the value, not a masked rendering of it, not a length.
    expect(screen.queryByTestId('token-secret')).toBeNull();
    expect(document.body.innerHTML).not.toContain(SENTINEL);
  });

  it('never shows a secret for a token the listing already holds', () => {
    // The listing is what a refetch produces, and it carries metadata alone.
    // If a secret could reach this component from a read, "once" would be a
    // claim rather than a property.
    panel();

    expect(screen.queryByTestId('token-secret')).toBeNull();
    expect(document.body.innerHTML).not.toContain(SENTINEL);
  });

  it('reports a refusal in the deployment’s own words', async () => {
    panel();
    answerWith({ ok: false, reachable: true, reason: 'that is not a permission' }, 400);

    await userEvent.type(screen.getByLabelText(LABELS.name), 'ci-runner');
    await userEvent.click(screen.getByTestId('issue-token'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(
      'that is not a permission',
    );
    expect(screen.queryByTestId('token-secret')).toBeNull();
  });
});

describe('revoking one', () => {
  it('names what stops before it stops it', async () => {
    panel();

    await userEvent.click(screen.getByTestId('revoke-token'));

    expect(screen.getByTestId('revoke-confirm')).toHaveTextContent(
      'stop authenticating now',
    );
    expect(sent).toHaveLength(0);
  });

  it('revokes nothing when the confirmation is dismissed', async () => {
    panel();

    await userEvent.click(screen.getByTestId('revoke-token'));
    await userEvent.click(screen.getByTestId('cancel-revoke'));

    expect(screen.queryByTestId('revoke-confirm')).toBeNull();
    expect(sent).toHaveLength(0);
  });

  it('revokes through the console’s own courier and marks the row', async () => {
    panel();
    answerWith({ ok: true, reachable: true, reason: '' });

    await userEvent.click(screen.getByTestId('revoke-token'));
    await userEvent.click(screen.getByTestId('confirm-revoke'));

    expect(sent.at(-1)?.method).toBe('DELETE');
    expect(sent.at(-1)?.url).toContain('token_id=tok-1');
    expect(await screen.findByText(LABELS.revoked)).toBeInTheDocument();
  });

  it('offers nothing to revoke on a token that is already revoked', () => {
    panel([
      {
        tokenId: 'tok-1',
        name: 'nightly-backup-checker',
        scopes: ['investigation.read'],
        revoked: true,
        expires: 'in 300 days',
      },
    ]);

    expect(screen.queryByTestId('revoke-token')).toBeNull();
    expect(screen.getByText(LABELS.revoked)).toBeInTheDocument();
  });
});

describe('a list that only ever grows', () => {
  const LIVE: IssuedToken = {
    tokenId: 'tok-live',
    name: 'nightly-backup-checker',
    scopes: ['investigation.read'],
    revoked: false,
    expires: 'in 300 days',
  };

  function revokedToken(tokenId: string): IssuedToken {
    return {
      tokenId,
      name: 'Console sign-in',
      scopes: [],
      revoked: true,
      expires: 'in 12 hours',
    };
  }

  it('collapses revoked tokens behind a disclosure named by how many there are', () => {
    panel([LIVE, revokedToken('tok-1'), revokedToken('tok-2')]);

    expect(screen.getByTestId('revoked-tokens')).toHaveTextContent('2 revoked');
    // Still in the document — a disclosure hides content visually, not from
    // the tree — so both revoked rows and the live one are all present.
    expect(screen.getAllByTestId('token')).toHaveLength(3);
  });

  it('draws no disclosure at all when nothing is revoked', () => {
    panel([LIVE]);

    expect(screen.queryByTestId('revoked-tokens')).toBeNull();
  });

  it('keeps a token just revoked in this session where it was, not inside the collapsed group', async () => {
    panel([LIVE]);

    await userEvent.click(screen.getByTestId('revoke-token'));
    answerWith({ ok: true, reachable: true, reason: '' });
    await userEvent.click(screen.getByTestId('confirm-revoke'));
    await screen.findByText(LABELS.revoked);

    expect(screen.queryByTestId('revoked-tokens')).toBeNull();
  });
});

describe('when the deployment cannot be reached', () => {
  it('says so on an issuance rather than reporting a refusal', async () => {
    panel();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.type(screen.getByLabelText(LABELS.name), 'ci-runner');
    await userEvent.click(screen.getByTestId('issue-token'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });

  it('says so on a revocation too, and leaves the row alone', async () => {
    panel();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('revoke-token'));
    await userEvent.click(screen.getByTestId('confirm-revoke'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
    expect(screen.queryByText(LABELS.revoked)).toBeNull();
  });

  it('reports a refused revocation in the deployment’s own words', async () => {
    panel();
    answerWith({ ok: false, reachable: true, reason: 'no live token' }, 404);

    await userEvent.click(screen.getByTestId('revoke-token'));
    await userEvent.click(screen.getByTestId('confirm-revoke'));

    expect(await screen.findByTestId('token-failure')).toHaveTextContent(
      'no live token',
    );
  });

  it('shows a token with no recorded expiry as one, rather than as blank', () => {
    panel([
      {
        tokenId: 'tok-2',
        name: 'no-expiry',
        scopes: [],
        revoked: false,
        expires: '',
      },
    ]);

    expect(screen.getByText(LABELS.none)).toBeInTheDocument();
  });

  it('holds back a secret an answer did not actually carry', async () => {
    panel();
    answerWith({ ok: true, reachable: true });

    await userEvent.type(screen.getByLabelText(LABELS.name), 'ci-runner');
    await userEvent.click(screen.getByTestId('issue-token'));

    expect(screen.queryByTestId('token-secret')).toBeNull();
  });
});
