'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select } from '@/components/form';

import { AUTONOMY_ENDPOINT } from './autonomy-editor';

/**
 * Widening what this node may do on its own, for a while, on the record.
 *
 * An override is the one write on this screen that is deliberately temporary —
 * it ends by itself — and the one the API refuses outright without a reason:
 * `reason` is required server-side, and the control refuses it first, before a
 * request carrying an empty one is ever sent. An override nobody explained is
 * one the next person cannot decide whether to renew, and the person who
 * granted it will not be the person who finds it still in force.
 *
 * Revoking is the other half, and it takes only a name: the deployment is the
 * one place that knows whether this node granted it. Asked to revoke one it
 * did not — an override inherited from above — it answers 404 with a reason
 * naming where it has to be revoked instead, and that sentence is rendered
 * exactly as it came back. This component has no opinion of its own about
 * inheritance; it is not its place to have one.
 */

export interface OverrideLabels {
  readonly grantTitle: string;
  readonly grantName: string;
  readonly grantLevel: string;
  readonly grantReason: string;
  readonly grantSeconds: string;
  readonly grant: string;
  readonly granting: string;
  readonly granted: string;
  readonly reasonRequired: string;
  readonly revokeTitle: string;
  readonly revokeName: string;
  readonly revoke: string;
  readonly revoking: string;
  readonly revoked: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface OverrideEditorProps {
  readonly nodeId: string;
  /** The levels the deployment declares, in the order it declares them. */
  readonly levels: readonly string[];
  /**
   * What each level permits, in words, keyed by the deployment's own slug.
   *
   * Optional because the deployment declares the levels and this console only
   * has words for the ones it knows: a level with no entry renders as its slug,
   * which is what every control here did before and is still usable.
   */
  readonly levelLabels?: Readonly<Record<string, string>>;
  readonly labels: OverrideLabels;
}

/** One request through the courier, reporting the deployment's own words on refusal. */
async function ask(
  nodeId: string,
  operation: string,
  payload: unknown,
  failed: string,
  unreachable: string,
  onFailure: (message: string) => void,
): Promise<unknown> {
  onFailure('');
  let response: Response;
  try {
    response = await fetch(AUTONOMY_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ nodeId, operation, payload }),
    });
  } catch {
    onFailure(unreachable);
    return null;
  }
  const body: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const reason: unknown = Reflect.get(Object(body), 'reason');
    onFailure(typeof reason === 'string' && reason !== '' ? reason : failed);
    return null;
  }
  return Reflect.get(Object(body), 'answer');
}

/** Grant an override with a reason on record, and revoke one by name. */
export function OverrideEditor({
  nodeId,
  levels,
  levelLabels,
  labels,
}: OverrideEditorProps): ReactNode {
  const [grantName, setGrantName] = useState('');
  const [grantLevel, setGrantLevel] = useState(levels[0] ?? '');
  const [grantReason, setGrantReason] = useState('');
  const [grantSeconds, setGrantSeconds] = useState('');
  const [grantBusy, setGrantBusy] = useState(false);
  const [grantSuccess, setGrantSuccess] = useState(false);
  const [grantFailure, setGrantFailure] = useState('');

  const [revokeName, setRevokeName] = useState('');
  const [revokeBusy, setRevokeBusy] = useState(false);
  const [revokeSuccess, setRevokeSuccess] = useState(false);
  const [revokeFailure, setRevokeFailure] = useState('');

  const reasonMissing = grantName.trim() !== '' && grantReason.trim() === '';
  const grantReady = grantName.trim() !== '' && grantReason.trim() !== '';

  async function grant(): Promise<void> {
    // The control's own refusal: the API requires a reason, and a request
    // carrying an empty one is never sent for the deployment to refuse instead.
    if (!grantReady) return;
    setGrantBusy(true);
    setGrantSuccess(false);
    const payload: Record<string, unknown> = {
      name: grantName,
      level: grantLevel,
      reason: grantReason,
    };
    const seconds = grantSeconds.trim();
    if (seconds !== '') {
      const parsed = Number(seconds);
      if (Number.isFinite(parsed)) payload.seconds = parsed;
    }
    const found = await ask(
      nodeId,
      'override',
      payload,
      labels.failed,
      labels.unreachable,
      setGrantFailure,
    );
    setGrantBusy(false);
    if (found === null) return;
    setGrantSuccess(true);
    setGrantName('');
    setGrantReason('');
    setGrantSeconds('');
  }

  async function revoke(): Promise<void> {
    if (revokeName.trim() === '') return;
    setRevokeBusy(true);
    setRevokeSuccess(false);
    const found = await ask(
      nodeId,
      'revoke-override',
      { name: revokeName },
      labels.failed,
      labels.unreachable,
      setRevokeFailure,
    );
    setRevokeBusy(false);
    if (found === null) return;
    setRevokeSuccess(true);
    setRevokeName('');
  }

  return (
    <div data-testid="override-editor" className="flex flex-col gap-5">
      <div className="flex flex-col gap-2" data-testid="override-grant">
        <h4 className="text-strong">{labels.grantTitle}</h4>
        <div className="flex flex-wrap items-end gap-3">
          <Input
            label={labels.grantName}
            name="override-name"
            value={grantName}
            onValueChange={(next) => {
              setGrantSuccess(false);
              setGrantName(next);
            }}
          />
          <Select
            label={labels.grantLevel}
            name="override-level"
            value={grantLevel}
            // Labelled where the words are, falling back to the slug for a level
            // this console has no words for — see `surfaces/postures.ts`.
            options={levels.map((level) => ({
              value: level,
              label: levelLabels?.[level] ?? level,
            }))}
            onValueChange={setGrantLevel}
          />
          <Input
            label={labels.grantReason}
            name="override-reason"
            value={grantReason}
            onValueChange={(next) => {
              setGrantSuccess(false);
              setGrantReason(next);
            }}
          />
          <Input
            label={labels.grantSeconds}
            name="override-seconds"
            type="number"
            value={grantSeconds}
            onValueChange={setGrantSeconds}
          />
          <Button
            data-testid="grant-override"
            state={grantBusy ? 'loading' : grantReady ? 'default' : 'disabled'}
            onClick={() => {
              void grant();
            }}
          >
            {grantBusy ? labels.granting : labels.grant}
          </Button>
        </div>
        {reasonMissing ? (
          <span data-testid="override-reason-required" className="text-meta text-muted">
            {labels.reasonRequired}
          </span>
        ) : null}
        {grantSuccess ? (
          <span data-testid="override-granted" className="text-meta text-success">
            {labels.granted}
          </span>
        ) : null}
        {grantFailure === '' ? null : (
          <span data-testid="override-grant-failure" className="text-meta text-danger">
            {grantFailure}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-2" data-testid="override-revoke">
        <h4 className="text-strong">{labels.revokeTitle}</h4>
        <div className="flex flex-wrap items-end gap-3">
          <Input
            label={labels.revokeName}
            name="revoke-name"
            value={revokeName}
            onValueChange={(next) => {
              setRevokeSuccess(false);
              setRevokeName(next);
            }}
          />
          <Button
            variant="destructive"
            data-testid="revoke-override"
            state={
              revokeBusy ? 'loading' : revokeName.trim() === '' ? 'disabled' : 'default'
            }
            onClick={() => {
              void revoke();
            }}
          >
            {revokeBusy ? labels.revoking : labels.revoke}
          </Button>
        </div>
        {revokeSuccess ? (
          <span data-testid="override-revoked" className="text-meta text-success">
            {labels.revoked}
          </span>
        ) : null}
        {revokeFailure === '' ? null : (
          <span data-testid="override-revoke-failure" className="text-meta text-danger">
            {revokeFailure}
          </span>
        )}
      </div>
    </div>
  );
}
