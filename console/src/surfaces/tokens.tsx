'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input } from '@/components/form';
import { Badge } from '@/components/status';

/**
 * Machine tokens: issued here, shown once, and revoked with the consequence named.
 *
 * **Once is structural, not a policy.** The deployment stores a hash and there
 * is no route that returns a secret, so the value exists in exactly one place
 * for exactly as long as this component holds it: React state, cleared by any
 * re-render that replaces it. It is not in the address, not in storage, not in a
 * server-rendered attribute, and it does not come back on a refresh — because
 * there is nowhere for it to come back from.
 *
 * **Revocation names what stops.** "Are you sure" is a question nobody has
 * answered no to. "Clients using this token stop authenticating now" is a
 * sentence somebody either accepts or does not, and it is the difference
 * between a decision and a click.
 *
 * **A browser sign-in is not a machine token, in anybody's head but the
 * store's.** `/identity/tokens` carries both under one shape, because the
 * gateway resolves a bearer the same way whichever one it is. This module
 * still knows the difference — `isConsoleSession` and `SessionPanel` below —
 * because the list a person reads has to sort by what a row *is*, not by what
 * table it came from.
 */

/** Where both writes go. The console's own process, forwarding once. */
export const TOKEN_ENDPOINT = '/api/token';

/**
 * The exact name `platform/identity/local_accounts.py` issues a sign-in token
 * under. Matched by value: the console has no import path to the platform's
 * own constant, and this is the one thing that has to stay a literal string.
 */
export const CONSOLE_SESSION_NAME = 'Console sign-in';

/** Whether `token` is a browser sign-in rather than a credential somebody minted. */
export function isConsoleSession(token: Pick<IssuedToken, 'name'>): boolean {
  return token.name === CONSOLE_SESSION_NAME;
}

export interface IssuedToken {
  readonly tokenId: string;
  readonly name: string;
  readonly scopes: readonly string[];
  readonly revoked: boolean;
  readonly expires: string;
}

export interface TokenLabels {
  readonly name: string;
  readonly issue: string;
  readonly issuing: string;
  readonly shownOnce: string;
  readonly revoke: string;
  readonly revoking: string;
  readonly revoked: string;
  readonly revokeConsequence: string;
  readonly revokeConfirm: string;
  readonly revokeCancel: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly none: string;
  /** Interpolates `{count}`, e.g. "12 revoked". Names the disclosure below the live list. */
  readonly revokedGroup: string;
  /** Column headers, shown once above the live list rather than guessed at per row. */
  readonly columnToken: string;
  readonly columnScopes: string;
  readonly columnExpires: string;
}

export interface TokenPanelProps {
  readonly tokens: readonly IssuedToken[];
  /**
   * What a token issued from this form actually carries: nothing is offered on
   * the form itself (see the module doc), so it is exactly this viewer's own
   * permissions — the ceiling `platform/identity/tokens.py` applies to an
   * unscoped token. Shown rather than left for the token list to answer later,
   * because "what will this be able to do" is the question at the point of
   * issuing it, not after.
   */
  readonly issuedScopes: readonly string[];
  readonly labels: TokenLabels;
}

/** Issue one, see its secret once, and revoke any of them. */
export function TokenPanel({
  tokens,
  issuedScopes,
  labels,
}: TokenPanelProps): ReactNode {
  const [name, setName] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState('');
  const [confirming, setConfirming] = useState('');
  const [gone, setGone] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState('');

  async function issue(): Promise<void> {
    setBusy('issue');
    setFailure('');
    setSecret('');
    let response: Response;
    try {
      response = await fetch(TOKEN_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ name, permissions: [] }),
      });
    } catch {
      setBusy('');
      setFailure(labels.unreachable);
      return;
    }
    const body: unknown = await response.json().catch(() => ({}));
    setBusy('');
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return;
    }
    const issued: unknown = Reflect.get(Object(body), 'secret');
    setSecret(typeof issued === 'string' ? issued : '');
    setName('');
  }

  async function revoke(tokenId: string): Promise<void> {
    setBusy(tokenId);
    setFailure('');
    let response: Response;
    try {
      response = await fetch(
        `${TOKEN_ENDPOINT}?token_id=${encodeURIComponent(tokenId)}`,
        {
          method: 'DELETE',
        },
      );
    } catch {
      setBusy('');
      setFailure(labels.unreachable);
      return;
    }
    const body: unknown = await response.json().catch(() => ({}));
    setBusy('');
    setConfirming('');
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return;
    }
    setGone((was) => [...was, tokenId]);
  }

  // Grouped by the token's own recorded state, not by `gone`: a token just
  // revoked in this session stays where the operator was looking at it,
  // showing its new status in place, rather than jumping into the collapsed
  // group the instant the confirmation is pressed.
  const live = tokens.filter((token) => !token.revoked);
  const revokedTokens = tokens.filter((token) => token.revoked);

  function row(token: IssuedToken): ReactNode {
    const revoked = token.revoked || gone.includes(token.tokenId);
    return (
      <li
        key={token.tokenId}
        data-testid="token"
        data-token={token.tokenId}
        className="flex flex-wrap items-center gap-3 min-w-0"
      >
        <span className="truncate">{token.name}</span>
        <span className="text-meta text-muted truncate">{token.scopes.join(', ')}</span>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {/* Never the secret. It was shown once, at issue, by the
              deployment — and never again by anything. */}
          <Badge status={revoked ? 'revoked' : 'healthy'} />
          <span className="text-meta text-muted">
            {token.expires === '' ? labels.none : token.expires}
          </span>
          {revoked ? (
            <span className="text-meta text-muted">{labels.revoked}</span>
          ) : confirming === token.tokenId ? (
            <span
              data-testid="revoke-confirm"
              role="alertdialog"
              aria-label={labels.revoke}
              className="flex flex-wrap items-center gap-2"
            >
              <span className="text-meta">{labels.revokeConsequence}</span>
              <Button
                variant="destructive"
                data-testid="confirm-revoke"
                state={busy === token.tokenId ? 'loading' : 'default'}
                onClick={() => {
                  void revoke(token.tokenId);
                }}
              >
                {labels.revokeConfirm}
              </Button>
              <Button
                data-testid="cancel-revoke"
                onClick={() => {
                  setConfirming('');
                }}
              >
                {labels.revokeCancel}
              </Button>
            </span>
          ) : (
            <button
              type="button"
              data-testid="revoke-token"
              data-token={token.tokenId}
              className="text-meta text-danger underline"
              onClick={() => {
                setConfirming(token.tokenId);
              }}
            >
              {labels.revoke}
            </button>
          )}
        </span>
      </li>
    );
  }

  return (
    <div data-testid="token-panel" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <Input
          label={labels.name}
          name="token-name"
          value={name}
          onValueChange={(next) => {
            setName(next);
            // Any edit clears the last secret. A value left on screen while
            // somebody types the next one is a value sitting in a shared room.
            setSecret('');
          }}
        />
        <Button
          variant="primary"
          data-testid="issue-token"
          state={
            busy === 'issue' ? 'loading' : name.trim() === '' ? 'disabled' : 'default'
          }
          onClick={() => {
            void issue();
          }}
        >
          {busy === 'issue' ? labels.issuing : labels.issue}
        </Button>
      </div>

      {/* The form offers no scope of its own — see the module doc — so this
          names the fixed one rather than leaving it to be discovered on the
          list below, once, after the fact. */}
      {issuedScopes.length === 0 ? null : (
        <p data-testid="token-issued-scopes" className="text-meta text-muted">
          {labels.columnScopes}: {issuedScopes.join(', ')}
        </p>
      )}

      {secret === '' ? null : (
        <div className="flex flex-col gap-1">
          <code className="text-small break-all" data-testid="token-secret">
            {secret}
          </code>
          <span className="text-meta text-warning">{labels.shownOnce}</span>
        </div>
      )}

      {live.length === 0 ? null : (
        <div
          data-testid="token-columns"
          className="flex flex-wrap items-center gap-3 text-meta text-muted"
        >
          <span className="truncate">{labels.columnToken}</span>
          <span className="ml-auto flex flex-wrap items-center gap-2">
            <span>{labels.columnScopes}</span>
            <span>{labels.columnExpires}</span>
          </span>
        </div>
      )}
      <ul className="flex flex-col gap-2 text-small">{live.map(row)}</ul>

      {/* Revoked tokens accumulate — every sign-in issues one — and a flat
          list that only ever grows is the same wall this console removed from
          Configuration and Catalogue. Collapsed by default because a revoked
          token is history, not something an operator triaging live access
          needs in front of them; the count says whether it is worth opening. */}
      {revokedTokens.length === 0 ? null : (
        <details data-testid="revoked-tokens">
          <summary className="cursor-pointer text-meta text-muted">
            {labels.revokedGroup.replace('{count}', String(revokedTokens.length))}
          </summary>
          <ul className="flex flex-col gap-2 text-small pt-2">
            {revokedTokens.map(row)}
          </ul>
        </details>
      )}

      {failure === '' ? null : (
        <span data-testid="token-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}

/**
 * One live browser sign-in, as the sessions panel groups it.
 *
 * `principalLabel` is resolved by the caller — the person's display name where
 * one is known, their id otherwise — because this component has no read of its
 * own to the principal list and a session grouped under a blank label is worse
 * than one grouped under an id.
 */
export interface SessionEntry {
  readonly tokenId: string;
  readonly principalId: string;
  readonly principalLabel: string;
  readonly expires: string;
}

export interface SessionLabels {
  readonly person: string;
  readonly expires: string;
  readonly endAll: string;
  readonly ending: string;
  readonly endConfirm: string;
  readonly endCancel: string;
  readonly endConsequence: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface SessionPanelProps {
  readonly sessions: readonly SessionEntry[];
  readonly labels: SessionLabels;
}

interface SessionGroup {
  readonly principalId: string;
  readonly principalLabel: string;
  readonly sessions: readonly SessionEntry[];
}

/** `sessions`, one group per person, in the order each person first appears. */
function grouped(sessions: readonly SessionEntry[]): readonly SessionGroup[] {
  const byPrincipal = new Map<string, SessionEntry[]>();
  for (const session of sessions) {
    const held = byPrincipal.get(session.principalId);
    if (held === undefined) {
      byPrincipal.set(session.principalId, [session]);
    } else {
      held.push(session);
    }
  }
  return [...byPrincipal.entries()].map(([principalId, held]) => ({
    principalId,
    principalLabel: held[0]?.principalLabel ?? principalId,
    sessions: held,
  }));
}

/**
 * Every live browser sign-in, one row per person, ended as a group.
 *
 * A person who signs in three times an hour holds three of these
 * simultaneously — each one a real, live credential until it is revoked or its
 * twelve hours pass — and grouping is what keeps that a number beside a name
 * rather than a wall of identical rows. "End all sessions" revokes every one
 * this person currently holds, in the one decision an operator actually has to
 * make: not this browser tab, but this person, everywhere.
 */
export function SessionPanel({ sessions, labels }: SessionPanelProps): ReactNode {
  const [busy, setBusy] = useState('');
  const [confirming, setConfirming] = useState('');
  const [gone, setGone] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState('');

  const groups = grouped(sessions.filter((session) => !gone.includes(session.tokenId)));

  async function endAll(group: SessionGroup): Promise<void> {
    setBusy(group.principalId);
    setFailure('');
    const ids = group.sessions.map((session) => session.tokenId);
    const responses = await Promise.all(
      ids.map((tokenId) =>
        fetch(`${TOKEN_ENDPOINT}?token_id=${encodeURIComponent(tokenId)}`, {
          method: 'DELETE',
        }).catch(() => null),
      ),
    );
    setBusy('');
    setConfirming('');
    if (responses.some((response) => response === null)) {
      setFailure(labels.unreachable);
      return;
    }
    if (responses.some((response) => response !== null && !response.ok)) {
      setFailure(labels.failed);
      return;
    }
    setGone((was) => [...was, ...ids]);
  }

  return (
    <div data-testid="session-panel" className="flex flex-col gap-3">
      {groups.length === 0 ? null : (
        <div
          data-testid="session-columns"
          className="flex flex-wrap items-center gap-3 text-meta text-muted"
        >
          <span className="truncate">{labels.person}</span>
          <span className="ml-auto">{labels.expires}</span>
        </div>
      )}
      <ul className="flex flex-col gap-2 text-small">
        {groups.map((group) => (
          <li
            key={group.principalId}
            data-testid="session-group"
            data-principal={group.principalId}
            className="flex flex-wrap items-center gap-3 min-w-0"
          >
            <span className="truncate">{group.principalLabel}</span>
            <span className="text-meta text-muted tabular-nums">
              {group.sessions.length}
            </span>
            <span className="ml-auto flex flex-wrap items-center gap-2">
              <span className="text-meta text-muted">
                {group.sessions[0]?.expires ?? ''}
              </span>
              {confirming === group.principalId ? (
                <span
                  data-testid="end-sessions-confirm"
                  role="alertdialog"
                  aria-label={labels.endAll}
                  className="flex flex-wrap items-center gap-2"
                >
                  <span className="text-meta">{labels.endConsequence}</span>
                  <Button
                    variant="destructive"
                    data-testid="confirm-end-sessions"
                    state={busy === group.principalId ? 'loading' : 'default'}
                    onClick={() => {
                      void endAll(group);
                    }}
                  >
                    {labels.endConfirm}
                  </Button>
                  <Button
                    data-testid="cancel-end-sessions"
                    onClick={() => {
                      setConfirming('');
                    }}
                  >
                    {labels.endCancel}
                  </Button>
                </span>
              ) : (
                <button
                  type="button"
                  data-testid="end-sessions"
                  data-principal={group.principalId}
                  className="text-meta text-danger underline"
                  onClick={() => {
                    setConfirming(group.principalId);
                  }}
                >
                  {labels.endAll}
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>

      {failure === '' ? null : (
        <span data-testid="session-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
