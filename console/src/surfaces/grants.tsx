'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select } from '@/components/form';
import { ConfirmDestructive } from '@/components/overlay';
import { Badge } from '@/components/status';

/**
 * A role grant: given to a principal, taken back, and refused for its own
 * reason when taking it back would leave nobody who could give it again.
 *
 * **The last-owner refusal is not a generic failure.** The gateway answers it
 * with a 409 and a sentence that names what to do about it — grant ownership
 * to somebody else first — and this component keeps that answer in a region of
 * its own rather than folding it into the same line an unreachable deployment
 * or an unknown role would use. A reader who sees "the deployment refused
 * this" learns nothing; a reader who sees the deployment's own sentence learns
 * what to do next.
 *
 * **A removal is destructive and confirms through the shared modal.** The
 * confirmation names the principal and the role, not "this grant" — the same
 * reason `ConfirmDestructive` takes a `target` rather than assuming one.
 *
 * **Absence, not disablement, is the caller's job.** `canWrite` decides
 * whether the form and the remove control exist at all; the list itself is
 * shown to anyone who can see this panel, because reading who holds what needs
 * `identity.read` alone.
 */

/** Where both writes go. The console's own process, forwarding once. */
export const GRANT_ENDPOINT = '/api/grants';

export interface Grant {
  readonly grantId: string;
  readonly principalId: string;
  readonly role: string;
  /** Empty means the grant covers the whole organisation. */
  readonly nodeId: string;
}

export interface GrantPrincipalOption {
  readonly id: string;
  readonly label: string;
}

export interface GrantLabels {
  readonly principal: string;
  readonly role: string;
  readonly node: string;
  readonly nodeHelp: string;
  readonly organisation: string;
  readonly add: string;
  readonly adding: string;
  readonly remove: string;
  readonly removing: string;
  readonly removeAction: string;
  readonly removeConsequence: string;
  readonly removeClose: string;
  readonly removeCancel: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface GrantPanelProps {
  readonly grants: readonly Grant[];
  readonly principals: readonly GrantPrincipalOption[];
  readonly roles: readonly string[];
  readonly canWrite: boolean;
  readonly labels: GrantLabels;
}

/** One field of `record`, read as a string, and the empty string when it is not one. */
function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

interface Answered {
  readonly reachable: boolean;
  readonly ok: boolean;
  readonly status: number;
  readonly reason: string;
  readonly answer: unknown;
}

async function ask(operation: string, payload: unknown): Promise<Answered> {
  let response: Response;
  try {
    response = await fetch(GRANT_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ operation, payload }),
    });
  } catch {
    return { reachable: false, ok: false, status: 0, reason: '', answer: undefined };
  }
  const body: unknown = await response.json().catch(() => ({}));
  const reason: unknown = Reflect.get(Object(body), 'reason');
  return {
    reachable: true,
    ok: response.ok,
    status: response.status,
    reason: typeof reason === 'string' ? reason : '',
    answer: Reflect.get(Object(body), 'answer'),
  };
}

/** Grant a role, see it land, and take one back — with its own room for the reason. */
export function GrantPanel({
  grants,
  principals,
  roles,
  canWrite,
  labels,
}: GrantPanelProps): ReactNode {
  const [principalId, setPrincipalId] = useState(principals[0]?.id ?? '');
  const [role, setRole] = useState(roles[0] ?? '');
  const [nodeId, setNodeId] = useState('');
  const [added, setAdded] = useState<readonly Grant[]>([]);
  const [gone, setGone] = useState<readonly string[]>([]);
  const [busy, setBusy] = useState('');
  const [confirming, setConfirming] = useState('');
  const [failure, setFailure] = useState('');
  // Kept apart from `failure` on purpose: the last-owner refusal is a
  // different message in its own region, not a colour on the same one.
  const [lastOwner, setLastOwner] = useState('');

  const rows = [...grants, ...added].filter((row) => !gone.includes(row.grantId));
  const confirmingGrant = rows.find((row) => row.grantId === confirming);

  async function grant(): Promise<void> {
    setBusy('add');
    setFailure('');
    setLastOwner('');
    const trimmedNode = nodeId.trim();
    const answered = await ask('add', {
      principal_id: principalId,
      role,
      ...(trimmedNode === '' ? {} : { node_id: trimmedNode }),
    });
    setBusy('');
    if (!answered.reachable) {
      setFailure(labels.unreachable);
      return;
    }
    if (!answered.ok) {
      setFailure(answered.reason === '' ? labels.failed : answered.reason);
      return;
    }
    const createdId = text(answered.answer, 'grant_id');
    if (createdId !== '') {
      setAdded((was) => [
        ...was,
        {
          grantId: createdId,
          principalId: text(answered.answer, 'principal_id'),
          role: text(answered.answer, 'role'),
          nodeId: text(answered.answer, 'node_id'),
        },
      ]);
    }
    setNodeId('');
  }

  async function remove(grantId: string): Promise<void> {
    setBusy(grantId);
    setFailure('');
    setLastOwner('');
    const answered = await ask('remove', { grant_id: grantId });
    setBusy('');
    if (!answered.reachable) {
      setFailure(labels.unreachable);
      return;
    }
    if (!answered.ok) {
      const reason = answered.reason === '' ? labels.failed : answered.reason;
      // The one refusal named for what it is: leaving the organisation with no
      // owner. Everything else — a role rejected, a connection that never
      // landed — stays in `failure`.
      if (answered.status === 409) {
        setLastOwner(reason);
      } else {
        setFailure(reason);
      }
      return;
    }
    setGone((was) => [...was, grantId]);
  }

  return (
    <div data-testid="grant-panel" className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2 text-small">
        {rows.map((row) => (
          <li
            key={row.grantId}
            data-testid="grant"
            data-grant={row.grantId}
            className="flex items-center gap-3 min-w-0"
          >
            <span className="font-mono truncate">{row.principalId}</span>
            <span className="ml-auto flex items-center gap-2">
              <Badge status={row.role} />
              <span className="text-meta text-muted">
                {row.nodeId === '' ? labels.organisation : row.nodeId}
              </span>
              {!canWrite ? null : busy === row.grantId ? (
                <span className="text-meta text-muted">{labels.removing}</span>
              ) : (
                <button
                  type="button"
                  data-testid="remove-grant"
                  data-grant={row.grantId}
                  className="text-meta text-danger underline"
                  onClick={() => {
                    setConfirming(row.grantId);
                  }}
                >
                  {labels.remove}
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>

      {!canWrite ? null : (
        <div className="flex flex-wrap items-end gap-3">
          <Select
            label={labels.principal}
            name="grant-principal"
            options={principals.map((option) => ({
              value: option.id,
              label: option.label,
            }))}
            value={principalId}
            onValueChange={setPrincipalId}
          />
          <Select
            label={labels.role}
            name="grant-role"
            options={roles.map((name) => ({ value: name, label: name }))}
            value={role}
            onValueChange={setRole}
          />
          <Input
            label={labels.node}
            name="grant-node"
            description={labels.nodeHelp}
            value={nodeId}
            onValueChange={setNodeId}
          />
          <Button
            variant="primary"
            data-testid="add-grant"
            state={
              busy === 'add'
                ? 'loading'
                : principalId === '' || role === ''
                  ? 'disabled'
                  : 'default'
            }
            onClick={() => {
              void grant();
            }}
          >
            {busy === 'add' ? labels.adding : labels.add}
          </Button>
        </div>
      )}

      {!canWrite ? null : (
        <ConfirmDestructive
          open={confirming !== ''}
          target={
            confirmingGrant === undefined
              ? confirming
              : `${confirmingGrant.principalId} — ${confirmingGrant.role}`
          }
          action={labels.removeAction}
          consequence={labels.removeConsequence}
          labels={{ close: labels.removeClose, cancel: labels.removeCancel }}
          onConfirm={() => {
            const grantId = confirming;
            setConfirming('');
            void remove(grantId);
          }}
          onCancel={() => {
            setConfirming('');
          }}
        />
      )}

      {lastOwner === '' ? null : (
        <p data-testid="grant-last-owner" className="text-meta text-warning">
          {lastOwner}
        </p>
      )}
      {failure === '' ? null : (
        <p data-testid="grant-failure" className="text-meta text-danger">
          {failure}
        </p>
      )}
    </div>
  );
}
