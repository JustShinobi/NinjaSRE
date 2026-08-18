import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SessionPanel, TokenPanel, type SessionEntry } from '@/surfaces/tokens';
import { isConsoleSession, type IssuedToken } from '@/surfaces/token-identity';

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

/**
 * `element`, or a failure naming the absence.
 *
 * A test that indexes into an array and asserts on `undefined` reports "cannot
 * read property of undefined", which says nothing about what the console did.
 * This says the element was not there.
 */
function one(elements: readonly HTMLElement[]): HTMLElement {
  const found = elements[0];
  if (found === undefined)
    throw new Error('the element this test is about is not there');
  return found;
}

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
  columnToken: 'Token',
  columnScopes: 'Scopes',
  columnExpires: 'Expires',
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

function panel(
  tokens: readonly IssuedToken[] = TOKENS,
  issuedScopes: readonly string[] = [],
): void {
  render(<TokenPanel tokens={tokens} issuedScopes={issuedScopes} labels={LABELS} />);
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

describe('what a token issued here actually holds', () => {
  it('names the fixed scope, since the form does not ask for one', () => {
    panel(TOKENS, ['investigation.read', 'token.manage']);

    expect(screen.getByTestId('token-issued-scopes')).toHaveTextContent(
      'investigation.read, token.manage',
    );
  });

  it('says nothing about a scope when this viewer holds none', () => {
    panel(TOKENS, []);

    expect(screen.queryByTestId('token-issued-scopes')).toBeNull();
  });
});

describe('columns a value alone cannot explain', () => {
  it('names what each column is, above the live list', () => {
    panel();

    const columns = screen.getByTestId('token-columns');
    expect(columns).toHaveTextContent(LABELS.columnToken);
    expect(columns).toHaveTextContent(LABELS.columnScopes);
    expect(columns).toHaveTextContent(LABELS.columnExpires);
  });

  it('draws no header at all over an empty list', () => {
    panel([]);

    expect(screen.queryByTestId('token-columns')).toBeNull();
  });
});

describe('telling a session from a machine token', () => {
  it('recognises the exact name a local sign-in issues its token under', () => {
    expect(isConsoleSession({ name: 'Console sign-in' })).toBe(true);
  });

  it('treats anything else as a credential somebody minted', () => {
    expect(isConsoleSession({ name: 'nightly-backup-checker' })).toBe(false);
    expect(isConsoleSession({ name: '' })).toBe(false);
  });
});

describe('active sessions, grouped by who holds them', () => {
  const SESSION_LABELS = {
    person: 'Principal',
    origin: 'Started',
    expires: 'Expires',
    endAll: 'Revoke',
    ending: 'Revoking…',
    endConfirm: 'Revoke it',
    endCancel: 'Leave it working',
    endConsequence: 'Clients using this token stop authenticating now.',
    failed: 'The deployment refused this.',
    unreachable: 'The deployment could not be reached.',
  };

  const SESSIONS: readonly SessionEntry[] = [
    {
      tokenId: 'sess-1',
      principalId: 'ana',
      principalLabel: 'Ana',
      expires: 'in 4 hours',
      origin: 'started 40 days ago',
    },
    {
      tokenId: 'sess-2',
      principalId: 'ana',
      principalLabel: 'Ana',
      expires: 'in 11 hours',
      origin: 'started 12 days ago',
    },
    {
      tokenId: 'sess-3',
      principalId: 'ben',
      principalLabel: 'Ben',
      expires: 'in 2 hours',
      origin: 'started 4 days ago',
    },
  ];

  function sessions(list: readonly SessionEntry[] = SESSIONS): void {
    render(<SessionPanel sessions={list} labels={SESSION_LABELS} />);
  }

  it('collapses three logins by the same person into one row', () => {
    sessions();

    const groups = screen.getAllByTestId('session-group');
    expect(groups).toHaveLength(2);
    expect(screen.getByText('Ana')).toBeInTheDocument();
    expect(screen.getByText('Ben')).toBeInTheDocument();
  });

  it("names the origin the group's first session started from, not a bare number", () => {
    sessions();

    // Ana's group is first — `grouped()` preserves first-appearance order —
    // and its first session is `sess-1`, so its origin is `sess-1`'s.
    const origins = screen.getAllByTestId('session-origin');
    expect(origins).toHaveLength(2);
    expect(origins[0]).toHaveTextContent('started 40 days ago');
    expect(origins[1]).toHaveTextContent('started 4 days ago');

    // "Not a bare number": nothing beside the person's name may be a loose
    // integer, labelled or not — Ana holds two sessions and Ben holds one,
    // so a value of exactly "2" or "1" sitting on its own is the historical
    // defect (the session count, rendered with no label of its own)
    // reappearing. Checked element by element, one top-level value at a
    // time, because the real values here ("in 4 hours") carry digits too
    // and a substring match on the row's concatenated text would not tell
    // the two apart.
    for (const group of screen.getAllByTestId('session-group')) {
      for (const value of Array.from(group.children)) {
        expect(value.textContent.trim()).not.toMatch(/^\d+$/);
      }
    }
  });

  it('names a column for the origin, beside who holds the session', () => {
    sessions();

    const columns = screen.getByTestId('session-columns');
    expect(columns).toHaveTextContent(SESSION_LABELS.origin);

    // "Beside who holds the session": the origin value must sit in the same
    // top-level slot of the row that the origin label sits in within the
    // header — the person's name alone in one slot, origin and expiry
    // together in the next — or the two no longer correspond and a reader
    // cannot tell which value under the header is which.
    const originSlot = Array.from(columns.children).findIndex((child) =>
      child.textContent.includes(SESSION_LABELS.origin),
    );
    expect(originSlot).toBeGreaterThanOrEqual(0);

    for (const group of screen.getAllByTestId('session-group')) {
      const origin = within(group).getByTestId('session-origin');
      const originValueSlot = Array.from(group.children).findIndex((child) =>
        child.contains(origin),
      );
      expect(originValueSlot).toBe(originSlot);
    }
  });

  it('names what stops before it stops it, for the whole group', async () => {
    sessions();

    await userEvent.click(one(screen.getAllByTestId('end-sessions')));

    expect(screen.getByTestId('end-sessions-confirm')).toHaveTextContent(
      'stop authenticating now',
    );
    expect(sent).toHaveLength(0);
  });

  it('ends every session a person holds in one confirmation', async () => {
    sessions();
    answerWith({ ok: true, reachable: true, reason: '' });

    await userEvent.click(one(screen.getAllByTestId('end-sessions')));
    await userEvent.click(screen.getByTestId('confirm-end-sessions'));

    await screen.findByText('Ben');
    expect(screen.queryByText('Ana')).toBeNull();
    expect(sent.map((call) => call.method)).toEqual(['DELETE', 'DELETE']);
    expect(sent.some((call) => call.url.includes('token_id=sess-1'))).toBe(true);
    expect(sent.some((call) => call.url.includes('token_id=sess-2'))).toBe(true);
  });

  it('ends nothing when the confirmation is dismissed', async () => {
    sessions();

    await userEvent.click(one(screen.getAllByTestId('end-sessions')));
    await userEvent.click(screen.getByTestId('cancel-end-sessions'));

    expect(screen.queryByTestId('end-sessions-confirm')).toBeNull();
    expect(sent).toHaveLength(0);
  });

  it('says the deployment could not be reached, and leaves the group alone', async () => {
    sessions();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(one(screen.getAllByTestId('end-sessions')));
    await userEvent.click(screen.getByTestId('confirm-end-sessions'));

    expect(await screen.findByTestId('session-failure')).toHaveTextContent(
      SESSION_LABELS.unreachable,
    );
    expect(screen.getByText('Ana')).toBeInTheDocument();
  });

  it('draws no column header at all over an empty list', () => {
    sessions([]);

    expect(screen.queryByTestId('session-columns')).toBeNull();
  });
});
