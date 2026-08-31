'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';
import { Textarea } from '@/components/form';

/**
 * The "precisa de você" band's own approve and reject controls.
 *
 * `Main.dc.html` draws the band as three flat controls -- Aprovar, Recusar,
 * Ver plano -- with no reason field sitting open beside them. Reject opens
 * its own reason field and submit only once clicked, and the submit stays
 * disabled until a reason is typed. That is a different sequence than
 * `IncidentDecisionControls` (the incident page's own card, which shows the
 * reason field from the start) uses for the same kind of decision, so this is
 * its own small component rather than a third mode bolted onto that one --
 * over the identical courier both already agree on: `POST /api/approval`,
 * addressing `POST /v1/approvals/{approval_id}/decision`. Neither control
 * carries the action out; approving only records the decision.
 */

export interface AttentionDecisionLabels {
  readonly approve: string;
  readonly reject: string;
  readonly reason: string;
  readonly submit: string;
  readonly cancel: string;
  readonly reasonRequired: string;
  readonly failed: string;
}

export interface AttentionDecisionControlsProps {
  /** The approval this decision answers -- what `/api/approval` addresses. */
  readonly approvalId: string;
  readonly labels: AttentionDecisionLabels;
}

/** Approve, or open a reason field and reject -- without leaving the Painel. */
export function AttentionDecisionControls({
  approvalId,
  labels,
}: AttentionDecisionControlsProps): ReactNode {
  const router = useRouter();
  const [rejecting, setRejecting] = useState(false);
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
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 flex-wrap">
        <Button
          variant="primary"
          data-testid="attention-approve"
          state={sending ? 'loading' : 'default'}
          onClick={() => {
            void decide('approve');
          }}
        >
          {labels.approve}
        </Button>
        {rejecting ? null : (
          <Button
            variant="secondary"
            data-testid="attention-reject"
            state={sending ? 'loading' : 'default'}
            onClick={() => {
              setRejecting(true);
            }}
          >
            {labels.reject}
          </Button>
        )}
      </div>
      {rejecting ? (
        <div className="flex flex-col gap-2 max-w-prose">
          <Textarea
            label={labels.reason}
            name="attention-reject-reason"
            rows={2}
            value={reason}
            onValueChange={setReason}
            data-testid="attention-reject-reason"
          />
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="secondary"
              data-testid="attention-reject-submit"
              state={sending ? 'loading' : rejectable ? 'default' : 'disabled'}
              onClick={() => {
                void decide('reject');
              }}
            >
              {labels.submit}
            </Button>
            <Button
              variant="quiet"
              onClick={() => {
                setRejecting(false);
                setReason('');
              }}
            >
              {labels.cancel}
            </Button>
            {rejectable ? null : (
              <span className="text-meta text-muted">{labels.reasonRequired}</span>
            )}
          </div>
        </div>
      ) : null}
      {failed ? (
        <p data-testid="attention-decision-failed" className="text-meta text-danger">
          {labels.failed}
        </p>
      ) : null}
    </div>
  );
}
