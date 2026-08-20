'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';
import { Textarea } from '@/components/form';

/**
 * The proposed-action card's two controls: approve and run, or reject with a
 * reason — decided on the incident page itself, never behind a navigation.
 *
 * Deliberately not `DecisionControls` (`surfaces/decision.tsx`), which
 * addresses a paused agent *interaction* through `/api/decision`. A proposed
 * remediation is an `ApprovalRequest` decided directly at the approval store,
 * not an interaction a live investigation is waiting on, and the two courier
 * routes behind them address different backend endpoints for that reason. The
 * two components share a shape — a reason that gates the reject control —
 * because that is the one thing both screens genuinely have in common.
 *
 * **Neither control executes anything itself.** Approving records the
 * decision at the deployment; carrying the action out is a separate mechanism
 * this screen does not invoke. The button's own label says "run" because that
 * is what the decision authorises, not because clicking it runs anything here.
 */

export interface DecisionControlLabels {
  readonly approve: string;
  readonly reject: string;
  readonly reason: string;
  readonly reasonRequired: string;
  readonly failed: string;
}

export interface IncidentDecisionControlsProps {
  /** The approval this decision answers, which is what the API is addressed by. */
  readonly approvalId: string;
  readonly labels: DecisionControlLabels;
}

/** Approve and run, or reject with a reason — without leaving the incident page. */
export function IncidentDecisionControls({
  approvalId,
  labels,
}: IncidentDecisionControlsProps): ReactNode {
  const router = useRouter();
  const [reason, setReason] = useState('');
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function decide(verdict: 'approve' | 'reject'): Promise<void> {
    setSending(true);
    setFailed(false);
    const response = await fetch('/api/approval', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        operation: 'decide',
        target: approvalId,
        payload: { verdict, reason },
      }),
    }).catch(() => null);
    setSending(false);
    if (response?.ok === true) {
      router.refresh();
      return;
    }
    setFailed(true);
  }

  const rejectable = reason.trim() !== '';

  return (
    <div data-testid="proposed-action-decision" className="flex flex-col gap-3">
      <Textarea
        label={labels.reason}
        name="reason"
        rows={2}
        value={reason}
        onValueChange={setReason}
      />
      <div className="flex items-center gap-2 flex-wrap">
        <Button
          variant="primary"
          data-testid="decision-control"
          state={sending ? 'loading' : 'default'}
          onClick={() => {
            void decide('approve');
          }}
        >
          {labels.approve}
        </Button>
        <Button
          variant="secondary"
          data-testid="decision-control"
          state={sending ? 'loading' : rejectable ? 'default' : 'disabled'}
          onClick={() => {
            void decide('reject');
          }}
        >
          {labels.reject}
        </Button>
        {rejectable ? null : (
          <span className="text-meta text-muted">{labels.reasonRequired}</span>
        )}
      </div>
      {failed ? (
        <p data-testid="decision-failed" className="text-meta text-danger">
          {labels.failed}
        </p>
      ) : null}
    </div>
  );
}
