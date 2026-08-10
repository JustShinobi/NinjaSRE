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
 */

/** Where both writes go. The console's own process, forwarding once. */
export const TOKEN_ENDPOINT = '/api/token';

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
}

export interface TokenPanelProps {
  readonly tokens: readonly IssuedToken[];
  readonly labels: TokenLabels;
}

/** Issue one, see its secret once, and revoke any of them. */
export function TokenPanel({ tokens, labels }: TokenPanelProps): ReactNode {
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

      {secret === '' ? null : (
        <div className="flex flex-col gap-1">
          <code className="text-small break-all" data-testid="token-secret">
            {secret}
          </code>
          <span className="text-meta text-warning">{labels.shownOnce}</span>
        </div>
      )}

      <ul className="flex flex-col gap-2 text-small">
        {tokens.map((token) => {
          const revoked = token.revoked || gone.includes(token.tokenId);
          return (
            <li
              key={token.tokenId}
              data-testid="token"
              data-token={token.tokenId}
              className="flex flex-wrap items-center gap-3 min-w-0"
            >
              <span className="truncate">{token.name}</span>
              <span className="text-meta text-muted truncate">
                {token.scopes.join(', ')}
              </span>
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
        })}
      </ul>

      {failure === '' ? null : (
        <span data-testid="token-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
