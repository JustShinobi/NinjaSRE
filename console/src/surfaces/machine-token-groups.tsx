'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Checkbox, Input } from '@/components/form';
import { Badge } from '@/components/status';
import { TOKEN_ENDPOINT } from './tokens';

/**
 * Machine tokens, grouped by what they were issued for.
 *
 * **Grouped by purpose, not listed flat.** The purpose a token was issued
 * for is the only thing this console asks for on the form (`name`), and it
 * is also the field that repeats when the same purpose is issued for
 * again and again — ~15 identical "bootstrap" rows was the visible symptom.
 * Grouping is what turns that repetition into one row with a count, so the
 * list fits in a fold instead of a scrollbar.
 *
 * **A new issuance for a purpose that already has a live token supersedes
 * it**, server-side (`platform/identity/tokens.py`'s `TokenService.issue`,
 * asked to `supersede`). This panel declares that behaviour beside the form
 * before it happens and names what happened after it does — the response
 * carries which tokens were superseded, and a silent substitution would be
 * exactly the "acúmulo silencioso" the purpose of grouping this page exists
 * to end.
 *
 * **Scopes are chosen, not typed.** The ceiling a token may hold is this
 * viewer's own permission set — `platform/identity/tokens.py`'s `_scoped`
 * narrows to it regardless of what a caller asks for — so offering anything
 * wider would be a form whose extra options do nothing. Every one of the
 * viewer's permissions is offered as a checkbox, checked by default so the
 * unchanged form issues a token as wide as its owner, exactly like the
 * form it replaces did.
 */

export const TOKEN_ISSUE_ENDPOINT = '/api/token';
export const TOKEN_BULK_REVOKE_ENDPOINT = '/api/token/bulk-revoke';

/** One machine token, as this panel needs it — never a browser session. */
export interface MachineToken {
  readonly tokenId: string;
  readonly name: string;
  readonly description: string;
  readonly scopes: readonly string[];
  /** ISO instant, kept raw so this panel can order a group by it. */
  readonly createdAt: string;
  readonly lastUsed: string;
  readonly expires: string;
  readonly revoked: boolean;
}

export interface MachineTokenLabels {
  readonly purpose: string;
  readonly purposeHelp: string;
  readonly description: string;
  readonly scopes: string;
  readonly issue: string;
  readonly issuing: string;
  readonly shownOnce: string;
  readonly superseded: string;
  readonly revoke: string;
  readonly revoking: string;
  readonly revokeConsequence: string;
  readonly revokeConfirm: string;
  readonly revokeCancel: string;
  readonly revokeOlder: string;
  readonly revokingOlder: string;
  readonly revokeOlderConsequence: string;
  readonly revokeOlderConfirm: string;
  readonly revokeOlderCancel: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly none: string;
  readonly count: string;
  readonly lastUsedLabel: string;
  readonly neverUsed: string;
  readonly revokedGroup: string;
  readonly empty: string;
}

export interface MachineTokenGroupsProps {
  readonly tokens: readonly MachineToken[];
  /** The viewer's own permissions — the ceiling a new token may hold. */
  readonly issuedScopes: readonly string[];
  readonly labels: MachineTokenLabels;
}

/** `value`, with its separators opened into spaces and each word capitalised. */
function humanize(value: string): string {
  const words = value.split(/[._-]+/).filter((word) => word.length > 0);
  if (words.length === 0) return value;
  return words
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

interface Group {
  readonly purpose: string;
  readonly tokens: readonly MachineToken[];
}

/** `tokens`, one group per `name`, in the order each purpose first appears. */
function grouped(tokens: readonly MachineToken[]): readonly Group[] {
  const byPurpose = new Map<string, MachineToken[]>();
  for (const token of tokens) {
    const held = byPurpose.get(token.name);
    if (held === undefined) {
      byPurpose.set(token.name, [token]);
    } else {
      held.push(token);
    }
  }
  return [...byPurpose.entries()].map(([purpose, held]) => ({ purpose, tokens: held }));
}

/** `group`'s tokens, most recently created first. */
function byNewest(group: Group): readonly MachineToken[] {
  return [...group.tokens].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

async function post(
  url: string,
  body: unknown,
): Promise<{ reachable: boolean; ok: boolean; body: unknown }> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    return { reachable: false, ok: false, body: undefined };
  }
  const parsed: unknown = await response.json().catch(() => ({}));
  return { reachable: true, ok: response.ok, body: parsed };
}

/** Every machine token, grouped by purpose, issued with scopes chosen from a list. */
export function MachineTokenGroups({
  tokens,
  issuedScopes,
  labels,
}: MachineTokenGroupsProps): ReactNode {
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<ReadonlySet<string>>(new Set(issuedScopes));
  const [secret, setSecret] = useState('');
  const [supersededCount, setSupersededCount] = useState(0);
  const [busy, setBusy] = useState('');
  const [confirming, setConfirming] = useState('');
  const [gone, setGone] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState('');

  const live = tokens.filter(
    (token) => !token.revoked && !gone.includes(token.tokenId),
  );
  const revokedTokens = tokens.filter(
    (token) => token.revoked || gone.includes(token.tokenId),
  );
  const groups = grouped(live);

  async function issue(): Promise<void> {
    setBusy('issue');
    setFailure('');
    setSecret('');
    setSupersededCount(0);
    const { reachable, ok, body } = await post(TOKEN_ISSUE_ENDPOINT, {
      name,
      permissions: [...scopes],
    });
    setBusy('');
    if (!reachable) {
      setFailure(labels.unreachable);
      return;
    }
    if (!ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return;
    }
    const issued: unknown = Reflect.get(Object(body), 'secret');
    setSecret(typeof issued === 'string' ? issued : '');
    const superseded: unknown = Reflect.get(Object(body), 'superseded');
    setSupersededCount(Array.isArray(superseded) ? superseded.length : 0);
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
    setBusy('');
    setConfirming('');
    if (!response.ok) {
      setFailure(labels.failed);
      return;
    }
    setGone((was) => [...was, tokenId]);
  }

  async function revokeOlder(group: Group): Promise<void> {
    const ordered = byNewest(group);
    const older = ordered.slice(1).map((token) => token.tokenId);
    if (older.length === 0) return;
    setBusy(group.purpose);
    setFailure('');
    const { reachable, ok } = await post(TOKEN_BULK_REVOKE_ENDPOINT, {
      token_ids: older,
      reason: `kept only the newest token issued for ${group.purpose}`,
    });
    setBusy('');
    setConfirming('');
    if (!reachable) {
      setFailure(labels.unreachable);
      return;
    }
    if (!ok) {
      setFailure(labels.failed);
      return;
    }
    setGone((was) => [...was, ...older]);
  }

  function toggleScope(scope: string, checked: boolean): void {
    setScopes((was) => {
      const next = new Set(was);
      if (checked) {
        next.add(scope);
      } else {
        next.delete(scope);
      }
      return next;
    });
  }

  return (
    <div data-testid="machine-token-groups" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        <Input
          label={labels.purpose}
          name="token-purpose"
          description={labels.purposeHelp}
          value={name}
          onValueChange={(next) => {
            setName(next);
            setSecret('');
          }}
        />

        {issuedScopes.length === 0 ? null : (
          <fieldset className="flex flex-col gap-1">
            <legend className="text-meta text-muted">{labels.scopes}</legend>
            <div className="flex flex-wrap gap-3">
              {issuedScopes.map((scope) => (
                <Checkbox
                  key={scope}
                  label={humanize(scope)}
                  name={`scope-${scope}`}
                  checked={scopes.has(scope)}
                  onCheckedChange={(checked) => {
                    toggleScope(scope, checked);
                  }}
                />
              ))}
            </div>
          </fieldset>
        )}

        <div>
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
            {supersededCount === 0 ? null : (
              <span
                data-testid="token-superseded-notice"
                className="text-meta text-muted"
              >
                {labels.superseded.replace('{count}', String(supersededCount))}
              </span>
            )}
          </div>
        )}
      </div>

      {groups.length === 0 ? (
        <p className="text-small text-muted">{labels.empty}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {groups.map((group) => {
            const ordered = byNewest(group);
            const newest = ordered[0];
            const lastUsed =
              ordered.find((token) => token.lastUsed !== '')?.lastUsed ?? '';
            const scopeUnion = [
              ...new Set(group.tokens.flatMap((token) => token.scopes)),
            ];
            return (
              <li
                key={group.purpose}
                data-testid="token-group"
                data-purpose={group.purpose}
                className="flex flex-col gap-2 bg-sunken rounded-3 p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-strong truncate">{group.purpose}</span>
                  <Badge status="healthy" />
                  <span
                    data-testid="token-group-count"
                    className="text-meta text-muted tabular-nums"
                  >
                    {labels.count.replace('{count}', String(group.tokens.length))}
                  </span>
                  <span className="ml-auto flex items-center gap-2">
                    {group.tokens.length > 1 ? (
                      confirming === group.purpose ? (
                        <span
                          data-testid="revoke-older-confirm"
                          role="alertdialog"
                          aria-label={labels.revokeOlder}
                          className="flex flex-wrap items-center gap-2"
                        >
                          <span className="text-meta">
                            {labels.revokeOlderConsequence}
                          </span>
                          <Button
                            variant="destructive"
                            data-testid="confirm-revoke-older"
                            state={busy === group.purpose ? 'loading' : 'default'}
                            onClick={() => {
                              void revokeOlder(group);
                            }}
                          >
                            {labels.revokeOlderConfirm}
                          </Button>
                          <Button
                            data-testid="cancel-revoke-older"
                            onClick={() => {
                              setConfirming('');
                            }}
                          >
                            {labels.revokeOlderCancel}
                          </Button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          data-testid="revoke-older"
                          data-purpose={group.purpose}
                          className="text-meta text-danger underline"
                          onClick={() => {
                            setConfirming(group.purpose);
                          }}
                        >
                          {labels.revokeOlder}
                        </button>
                      )
                    ) : null}
                  </span>
                </div>

                <span className="text-meta text-muted truncate">
                  {scopeUnion.map(humanize).join(', ')}
                </span>
                <span className="text-meta text-muted">
                  {labels.lastUsedLabel}:{' '}
                  {lastUsed === '' ? labels.neverUsed : lastUsed}
                </span>
                {newest?.description === '' ||
                newest?.description === undefined ? null : (
                  <span className="text-meta text-muted truncate">
                    {newest.description}
                  </span>
                )}

                <details data-testid="token-group-detail">
                  <summary className="cursor-pointer text-meta text-muted">
                    {labels.description}
                  </summary>
                  <ul className="flex flex-col gap-2 pt-2 text-small">
                    {ordered.map((token) => (
                      <li
                        key={token.tokenId}
                        data-testid="token"
                        data-token={token.tokenId}
                        className="flex flex-wrap items-center gap-3 min-w-0"
                      >
                        <span className="text-meta text-muted">
                          {token.expires === '' ? labels.none : token.expires}
                        </span>
                        {confirming === token.tokenId ? (
                          <span
                            data-testid="revoke-confirm"
                            role="alertdialog"
                            aria-label={labels.revoke}
                            className="ml-auto flex flex-wrap items-center gap-2"
                          >
                            <span className="text-meta">
                              {labels.revokeConsequence}
                            </span>
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
                            className="ml-auto text-meta text-danger underline"
                            onClick={() => {
                              setConfirming(token.tokenId);
                            }}
                          >
                            {labels.revoke}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            );
          })}
        </ul>
      )}

      {revokedTokens.length === 0 ? null : (
        <details data-testid="revoked-tokens">
          <summary className="cursor-pointer text-meta text-muted">
            {labels.revokedGroup.replace('{count}', String(revokedTokens.length))}
          </summary>
          <ul className="flex flex-col gap-2 pt-2 text-small">
            {revokedTokens.map((token) => (
              <li key={token.tokenId} data-testid="token" data-token={token.tokenId}>
                <span className="truncate">{token.name}</span>
              </li>
            ))}
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
