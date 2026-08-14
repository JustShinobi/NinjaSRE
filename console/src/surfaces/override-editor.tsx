'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select } from '@/components/form';
import { Badge } from '@/components/status';

import { AUTONOMY_ENDPOINT } from './autonomy-editor';

/**
 * Widening what this node may do on its own, for a while, on the record.
 *
 * An override is the one write on this screen that is deliberately temporary —
 * it ends by itself — and the one the API refuses outright without a reason:
 * `reason` is required server-side, and the control refuses it first, before a
 * request carrying an empty one is ever sent. An override nobody explained is
 * one the next person cannot decide whether to renew, and the person who
 * granted it will not be the person who finds it still in force. The duration
 * is a preset (an hour, a shift, a day) rather than a raw number of seconds,
 * because "how long" is a decision an operator makes in units they think in;
 * a custom value is still there for the one case a preset does not cover.
 *
 * Revoking is a click on the override itself, never a name typed from memory:
 * every override this node's own bounds report — including one inherited from
 * a parent node — is listed here, each with its own control. The deployment is
 * the one place that knows whether *this* node granted it, so a click on an
 * inherited override still asks; it just answers 404 with a reason naming
 * where the override has to be revoked instead, and that sentence is rendered
 * exactly as it came back. This component has no opinion of its own about
 * inheritance; it is not its place to have one.
 */

export interface OverrideLabels {
  readonly grantTitle: string;
  readonly grantName: string;
  readonly grantNameHelp: string;
  readonly grantLevel: string;
  readonly grantReason: string;
  readonly grantReasonHelp: string;
  readonly grantDuration: string;
  readonly grantDurationDefault: string;
  readonly grantDurationOneHour: string;
  readonly grantDurationEightHours: string;
  readonly grantDurationTwentyFourHours: string;
  readonly grantDurationCustom: string;
  readonly grantSeconds: string;
  readonly grant: string;
  readonly granting: string;
  readonly granted: string;
  readonly reasonRequired: string;
  readonly revokeTitle: string;
  /** Shown instead of the list when this node's bounds hold no active override. */
  readonly revokeEmpty: string;
  /** "Expires" — the same word the bounds panel already uses for the same fact. */
  readonly duration: string;
  /** "Granted because" — the same word the bounds panel already uses. */
  readonly reasonLabel: string;
  /** "Granted by" — who to ask before taking a colleague's override away. */
  readonly grantedBy: string;
  readonly revoke: string;
  readonly revoking: string;
  readonly revoked: string;
  readonly failed: string;
  readonly unreachable: string;
}

/** One override this node's bounds currently report, ready to revoke with a click. */
export interface ActiveOverride {
  readonly name: string;
  readonly level: string;
  readonly expiresIso: string;
  readonly expiresRelative: string;
  readonly expiresAbsolute: string;
  readonly reason: string;
  /** The principal who granted it, or `''` when the deployment did not say. */
  readonly grantedBy: string;
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
  /**
   * Every override this node's own bounds currently report, resolved and
   * formatted by the screen that has a locale and a clock — this component has
   * neither. Revoking reads this list rather than a field a person typed into,
   * so there is nothing to remember and nothing to mistype.
   */
  readonly active: readonly ActiveOverride[];
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

/**
 * What each preset stands for. `''` (the deployment's own default) and
 * `'custom'` are not here: the first needs no `seconds` at all, and the second
 * reads the plain field instead.
 */
const PRESET_SECONDS: Readonly<Record<string, number>> = {
  '1h': 60 * 60,
  '8h': 8 * 60 * 60,
  '24h': 24 * 60 * 60,
};

/** The seconds a custom duration stands for, or `undefined` for a blank or unparseable one. */
function customSeconds(raw: string): number | undefined {
  const trimmed = raw.trim();
  if (trimmed === '') return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/** Grant an override with a reason on record, and revoke one by clicking it. */
export function OverrideEditor({
  nodeId,
  levels,
  levelLabels,
  active,
  labels,
}: OverrideEditorProps): ReactNode {
  const [grantName, setGrantName] = useState('');
  const [grantLevel, setGrantLevel] = useState(levels[0] ?? '');
  const [grantReason, setGrantReason] = useState('');
  /** `''` (the deployment's default), a preset key, or `'custom'`. */
  const [grantDuration, setGrantDuration] = useState('');
  const [grantSeconds, setGrantSeconds] = useState('');
  const [grantBusy, setGrantBusy] = useState(false);
  const [grantSuccess, setGrantSuccess] = useState(false);
  const [grantFailure, setGrantFailure] = useState('');

  /** The name currently being revoked, or `''` when nothing is in flight. */
  const [revokeBusy, setRevokeBusy] = useState('');
  /** Removed optimistically, on a successful answer, so a click cannot be repeated on a gone override. */
  const [revokedNames, setRevokedNames] = useState<readonly string[]>([]);
  const [revokeSuccessName, setRevokeSuccessName] = useState('');
  const [revokeFailure, setRevokeFailure] = useState('');

  const reasonMissing = grantName.trim() !== '' && grantReason.trim() === '';
  const grantReady = grantName.trim() !== '' && grantReason.trim() !== '';

  const visibleActive = active.filter(
    (override) => !revokedNames.includes(override.name),
  );

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
    const seconds =
      grantDuration === 'custom'
        ? customSeconds(grantSeconds)
        : PRESET_SECONDS[grantDuration];
    if (seconds !== undefined) payload.seconds = seconds;
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
    setGrantDuration('');
    setGrantSeconds('');
  }

  async function revoke(name: string): Promise<void> {
    setRevokeBusy(name);
    setRevokeSuccessName('');
    const found = await ask(
      nodeId,
      'revoke-override',
      { name },
      labels.failed,
      labels.unreachable,
      setRevokeFailure,
    );
    setRevokeBusy('');
    if (found === null) return;
    setRevokeSuccessName(name);
    setRevokedNames((was) => [...was, name]);
  }

  return (
    <div data-testid="override-editor" className="flex flex-col gap-5">
      <div className="flex flex-col gap-2" data-testid="override-grant">
        <h4 className="text-strong">{labels.grantTitle}</h4>
        <div className="flex flex-wrap items-end gap-3">
          <Input
            label={labels.grantName}
            name="override-name"
            description={labels.grantNameHelp}
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
            description={labels.grantReasonHelp}
            value={grantReason}
            onValueChange={(next) => {
              setGrantSuccess(false);
              setGrantReason(next);
            }}
          />
          <Select
            label={labels.grantDuration}
            name="override-duration"
            value={grantDuration}
            options={[
              { value: '', label: labels.grantDurationDefault },
              { value: '1h', label: labels.grantDurationOneHour },
              { value: '8h', label: labels.grantDurationEightHours },
              { value: '24h', label: labels.grantDurationTwentyFourHours },
              { value: 'custom', label: labels.grantDurationCustom },
            ]}
            onValueChange={setGrantDuration}
          />
          {grantDuration === 'custom' ? (
            <Input
              label={labels.grantSeconds}
              name="override-seconds"
              type="number"
              value={grantSeconds}
              onValueChange={setGrantSeconds}
            />
          ) : null}
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
        {visibleActive.length === 0 ? (
          <p data-testid="override-revoke-empty" className="text-meta text-muted">
            {labels.revokeEmpty}
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {visibleActive.map((override) => (
              <li
                key={override.name}
                data-testid="active-override"
                data-override={override.name}
                className="flex flex-wrap items-center gap-3"
              >
                <span className="font-mono min-w-0 truncate">{override.name}</span>
                <Badge status={override.level} />
                <span className="text-meta text-muted">
                  {labels.duration}{' '}
                  <time dateTime={override.expiresIso} title={override.expiresAbsolute}>
                    {override.expiresRelative}
                  </time>
                </span>
                {override.reason === '' ? null : (
                  <span className="text-meta text-muted">
                    {labels.reasonLabel} {override.reason}
                  </span>
                )}
                {override.grantedBy === '' ? null : (
                  <span className="text-meta text-muted">
                    {labels.grantedBy} {override.grantedBy}
                  </span>
                )}
                <Button
                  variant="destructive"
                  data-testid="revoke-override"
                  data-override={override.name}
                  state={revokeBusy === override.name ? 'loading' : 'default'}
                  onClick={() => {
                    void revoke(override.name);
                  }}
                >
                  {revokeBusy === override.name ? labels.revoking : labels.revoke}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {revokeSuccessName === '' ? null : (
          <span data-testid="override-revoked" className="text-meta text-success">
            {labels.revoked}
          </span>
        )}
        {revokeFailure === '' ? null : (
          <span data-testid="override-revoke-failure" className="text-meta text-danger">
            {revokeFailure}
          </span>
        )}
      </div>
    </div>
  );
}
