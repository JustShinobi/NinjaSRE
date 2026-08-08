'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';
import { Textarea } from '@/components/form';

/**
 * Approving or rejecting, on the page the decision is being read on.
 *
 * Decide-in-place rather than "open the approval to decide it": a queue that
 * takes a navigation per decision is a queue people work through by opening six
 * tabs, and six tabs is how the wrong one gets approved.
 *
 * **A rejection carries a reason and the control enforces it.** The reason is
 * what the next person reads when the same change is proposed again — a
 * rejection with no reason is indistinguishable from one nobody got to, and the
 * agent proposes it again next week either way. The route handler refuses one
 * without a reason too, because a control is a courtesy and a server check is a
 * rule.
 */

export interface DecisionLabels {
  readonly approve: string;
  readonly reject: string;
  readonly reason: string;
  readonly reasonRequired: string;
}

export interface DecisionControlsProps {
  /** The interaction this decision answers, which is what the API is addressed by. */
  readonly interactionId: string;
  readonly labels: DecisionLabels;
}

/** Approve, or reject with a reason, without leaving the page. */
export function DecisionControls({
  interactionId,
  labels,
}: DecisionControlsProps): ReactNode {
  const router = useRouter();
  const [reason, setReason] = useState('');
  const [sending, setSending] = useState(false);

  function decide(verdict: 'approve' | 'reject'): void {
    setSending(true);
    void fetch('/api/decision', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ interactionId, verdict, reason }),
    })
      .then(() => {
        router.refresh();
      })
      .finally(() => {
        setSending(false);
      });
  }

  const rejectable = reason.trim() !== '';

  return (
    <div data-testid="decision" className="flex flex-col gap-3">
      <Textarea
        label={labels.reason}
        name="reason"
        rows={2}
        value={reason}
        onValueChange={setReason}
      />
      <div className="flex items-center gap-3 flex-wrap">
        <Button
          variant="primary"
          data-testid="approve"
          state={sending ? 'loading' : 'default'}
          onClick={() => {
            decide('approve');
          }}
        >
          {labels.approve}
        </Button>
        <Button
          variant="destructive"
          data-testid="reject"
          state={sending ? 'loading' : rejectable ? 'default' : 'disabled'}
          onClick={() => {
            decide('reject');
          }}
        >
          {labels.reject}
        </Button>
        {rejectable ? null : (
          <span className="text-meta text-muted">{labels.reasonRequired}</span>
        )}
      </div>
    </div>
  );
}
