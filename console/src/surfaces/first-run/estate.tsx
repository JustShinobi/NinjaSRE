'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { StatusDot } from '@/components/status';
import { cx } from '@/design/cx';
import { AlertTriangleIcon } from '@/design/icons';

/**
 * Turning a hypervisor into an estate, in the order somebody would do it by hand.
 *
 * Three controls, and the middle one is the reason this is a screen rather than
 * a form.
 *
 * **Ask what the token may do.** The vendor is asked directly rather than
 * inferred from whether a call happened to succeed, and every privilege it does
 * not hold is named with the path it was needed on and a sentence saying what
 * stops working without it. "Insufficient privileges" sends an operator back to
 * a permissions screen to re-grant the role they already have; "Sys.Syslog on
 * /, without it nothing can read the cluster log" does not.
 *
 * A gap that only affects what a *later* feature would read is shown apart and
 * never blocks. An operator whose token reads their whole cluster must not be
 * told it is broken.
 *
 * **Look before committing.** The preview runs discovery and stores nothing:
 * the counts come back, the operator recognises their own cluster, and if they
 * do not there is nothing to undo. A wizard that swept on submit would have
 * written a thousand rows before anybody had read a number.
 *
 * **Then commit.** Confirming registers the recurring sweep, and the control is
 * disabled until a preview has come back — not to be strict, but because the
 * preview is the only thing that makes confirming an informed act.
 */

export const ESTATE_ENDPOINT = '/api/estate';

export interface EstateStepLabels {
  readonly integration: string;
  readonly check: string;
  readonly checking: string;
  readonly recheck: string;
  readonly sufficient: string;
  readonly insufficient: string;
  readonly missingRead: string;
  readonly missingAdvisory: string;
  readonly grantedAt: string;
  readonly preview: string;
  readonly previewing: string;
  readonly found: string;
  readonly unplaced: string;
  readonly incomplete: string;
  readonly confirm: string;
  readonly confirming: string;
  readonly confirmed: string;
  readonly needsPreview: string;
  readonly refused: string;
  readonly unreachable: string;
}

export interface EstateStepProps {
  /** Which integration this estate comes from — the one whose credential is stored. */
  readonly integration: string;
  /** The declared networks, as CIDR to zone name. Empty until one is declared. */
  readonly zones: Readonly<Record<string, string>>;
  readonly labels: EstateStepLabels;
}

interface Privileges {
  readonly sufficient: boolean;
  readonly missingRead: readonly string[];
  readonly missingAdvisory: readonly string[];
  readonly grantedAt: string;
}

interface Counts {
  readonly nodes: number;
  readonly guests: number;
  readonly running: number;
  readonly zones: number;
  readonly unplaced: number;
  readonly complete: boolean;
}

type Phase = 'idle' | 'working' | 'refused' | 'unreachable';

function strings(record: unknown, name: string): readonly string[] {
  const found: unknown = Reflect.get(Object(record), name);
  return Array.isArray(found) ? found.filter((each) => typeof each === 'string') : [];
}

function count(record: unknown, name: string): number {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'number' ? found : 0;
}

async function ask(body: Record<string, unknown>): Promise<{
  ok: boolean;
  reachable: boolean;
  reason: string;
  result: unknown;
}> {
  const answer = await fetch(ESTATE_ENDPOINT, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload: unknown = await answer.json().catch(() => ({}));
  return {
    ok: Reflect.get(Object(payload), 'ok') === true,
    reachable: Reflect.get(Object(payload), 'reachable') !== false,
    reason: String(Reflect.get(Object(payload), 'reason') ?? ''),
    result: Reflect.get(Object(payload), 'result') ?? {},
  };
}

export function EstateStep({ integration, zones, labels }: EstateStepProps): ReactNode {
  const [phase, setPhase] = useState<Phase>('idle');
  const [reason, setReason] = useState('');
  const [privileges, setPrivileges] = useState<Privileges | null>(null);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [confirmed, setConfirmed] = useState('');

  const settle = (answer: {
    ok: boolean;
    reachable: boolean;
    reason: string;
  }): boolean => {
    if (!answer.reachable) {
      setPhase('unreachable');
      setReason('');
      return false;
    }
    if (!answer.ok) {
      setPhase('refused');
      setReason(answer.reason);
      return false;
    }
    setPhase('idle');
    setReason('');
    return true;
  };

  const check = async (): Promise<void> => {
    setPhase('working');
    const answer = await ask({ action: 'report', integration });
    if (!settle(answer)) return;
    const report: unknown = Reflect.get(Object(answer.result), 'report') ?? {};
    const held: unknown = Reflect.get(Object(report), 'privileges') ?? report;
    setPrivileges({
      sufficient: Reflect.get(Object(held), 'read_sufficient') === true,
      missingRead: strings(held, 'missing_read'),
      missingAdvisory: strings(held, 'missing_advisory'),
      grantedAt: String(Reflect.get(Object(held), 'granted_at') ?? ''),
    });
  };

  const preview = async (): Promise<void> => {
    setPhase('working');
    const answer = await ask({ action: 'preview', integration, zones });
    if (!settle(answer)) return;
    setCounts({
      nodes: count(answer.result, 'nodes'),
      guests: count(answer.result, 'guests'),
      running: count(answer.result, 'running'),
      zones: count(answer.result, 'zones'),
      unplaced: count(answer.result, 'unplaced'),
      complete: Reflect.get(Object(answer.result), 'complete') !== false,
    });
  };

  const confirm = async (): Promise<void> => {
    setPhase('working');
    const answer = await ask({ action: 'confirm', integration });
    if (!settle(answer)) return;
    setConfirmed(String(Reflect.get(Object(answer.result), 'job_id') ?? ''));
  };

  const busy = phase === 'working';

  return (
    <div className="flex flex-col gap-4" data-testid="estate-step">
      <p className="text-small text-muted" data-testid="estate-integration">
        {labels.integration.replace('{integration}', integration)}
      </p>

      {/* 1. What the token may do, asked of the cluster itself. */}
      <div className="flex flex-col gap-2">
        <Button
          onClick={() => {
            void check();
          }}
          state={busy ? 'loading' : 'default'}
          data-testid="estate-check"
        >
          {busy && privileges === null
            ? labels.checking
            : privileges === null
              ? labels.check
              : labels.recheck}
        </Button>

        {privileges === null ? null : (
          <div className="flex flex-col gap-2" data-testid="privilege-report">
            <span className="flex items-center gap-2 text-small">
              <StatusDot status={privileges.sufficient ? 'healthy' : 'degraded'} />
              <span data-testid="privilege-verdict">
                {privileges.sufficient ? labels.sufficient : labels.insufficient}
              </span>
            </span>

            {privileges.missingRead.length === 0 ? null : (
              <div className="flex flex-col gap-1" data-testid="privilege-missing">
                <span className="text-meta text-muted">{labels.missingRead}</span>
                <ul className="flex flex-col gap-1 text-small">
                  {privileges.missingRead.map((gap) => (
                    <li key={gap} data-testid="privilege-gap">
                      {gap}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {privileges.missingAdvisory.length === 0 ? null : (
              <div className="flex flex-col gap-1" data-testid="privilege-advisory">
                <span className="text-meta text-muted">{labels.missingAdvisory}</span>
                <ul className="flex flex-col gap-1 text-small">
                  {privileges.missingAdvisory.map((gap) => (
                    <li key={gap}>{gap}</li>
                  ))}
                </ul>
              </div>
            )}

            {privileges.grantedAt === '' ? null : (
              <p className="text-meta text-muted" data-testid="privilege-granted-at">
                {labels.grantedAt} {privileges.grantedAt}
              </p>
            )}
          </div>
        )}
      </div>

      {/* 2. What a sweep would find, with nothing stored. */}
      <div className="flex flex-col gap-2">
        <Button
          onClick={() => {
            void preview();
          }}
          state={busy ? 'loading' : 'default'}
          data-testid="estate-preview"
        >
          {busy && counts === null ? labels.previewing : labels.preview}
        </Button>

        {counts === null ? null : (
          <div className="flex flex-col gap-1" data-testid="estate-counts">
            <span className="text-small">
              {labels.found
                .replace('{nodes}', String(counts.nodes))
                .replace('{guests}', String(counts.guests))
                .replace('{running}', String(counts.running))
                .replace('{zones}', String(counts.zones))}
            </span>
            {counts.unplaced === 0 ? null : (
              <span className="text-meta text-muted" data-testid="estate-unplaced">
                {labels.unplaced.replace('{count}', String(counts.unplaced))}
              </span>
            )}
            {counts.complete ? null : (
              <span className="text-meta text-muted" data-testid="estate-incomplete">
                {labels.incomplete}
              </span>
            )}
          </div>
        )}
      </div>

      {/* 3. Committing to it, and not before there is something to commit to. */}
      <div className="flex flex-col gap-2">
        <Button
          onClick={() => {
            void confirm();
          }}
          state={busy || counts === null ? 'disabled' : 'default'}
          data-testid="estate-confirm"
        >
          {busy && confirmed === '' ? labels.confirming : labels.confirm}
        </Button>
        {counts === null ? (
          <span className="text-meta text-muted" data-testid="estate-needs-preview">
            {labels.needsPreview}
          </span>
        ) : null}
        {confirmed === '' ? null : (
          <span className="text-small" data-testid="estate-confirmed">
            {labels.confirmed}
          </span>
        )}
      </div>

      {/* Boxed, iconed, and `alert` rather than `status` — this used to be a
          bare, uncoloured line, which is a smaller version of the same
          defect the model step and the credential form had: a refusal that
          reads exactly like the rest of the page's quiet text. */}
      {phase === 'refused' ? (
        <p
          role="alert"
          data-testid="estate-refused"
          className={cx(
            'flex items-center gap-2 rounded-2 edge px-3 py-2 text-small',
            'bg-danger-bg text-danger border-danger',
          )}
        >
          <span aria-hidden="true">
            <AlertTriangleIcon />
          </span>
          {labels.refused} {reason}
        </p>
      ) : null}
      {phase === 'unreachable' ? (
        <p
          role="alert"
          data-testid="estate-unreachable"
          className={cx(
            'flex items-center gap-2 rounded-2 edge px-3 py-2 text-small',
            'bg-danger-bg text-danger border-danger',
          )}
        >
          <span aria-hidden="true">
            <AlertTriangleIcon />
          </span>
          {labels.unreachable}
        </p>
      ) : null}
    </div>
  );
}
