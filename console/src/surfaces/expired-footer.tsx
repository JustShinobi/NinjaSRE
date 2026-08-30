'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';

/**
 * The one exit an expired decision offers: propose again on a fresh reading,
 * or discard it.
 *
 * Both post through the same `/api/approval` courier `DecisionControls` and
 * `IncidentDecisionControls` already use, with a new operation each
 * (`repropose`, `discard`) rather than a new courier — one file forwarding
 * every decision-adjacent write, never a second opinion about how to reach
 * the approval store.
 *
 * On a successful repropose the page refreshes in place: the server
 * component re-reads `/v1/approvals` and the new pending decision is what
 * renders where this card was, with no navigation the operator has to make
 * themselves (AN-08).
 */

export interface ExpiredFooterLabels {
  readonly explanation: string;
  readonly repropose: string;
  readonly discard: string;
  readonly failed: string;
}

export interface ExpiredFooterProps {
  readonly approvalId: string;
  readonly labels: ExpiredFooterLabels;
}

export function ExpiredFooterControls({ approvalId, labels }: ExpiredFooterProps): ReactNode {
  const router = useRouter();
  const [busy, setBusy] = useState<'repropose' | 'discard' | null>(null);
  const [failed, setFailed] = useState(false);

  async function act(operation: 'repropose' | 'discard'): Promise<void> {
    setBusy(operation);
    setFailed(false);
    const response = await fetch('/api/approval', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ operation, target: approvalId, payload: {} }),
    }).catch(() => null);
    setBusy(null);
    if (response?.ok === true) {
      router.refresh();
      return;
    }
    setFailed(true);
  }

  return (
    <div
      data-testid="expired-footer"
      className="flex items-center gap-3 px-5 py-3 rounded-b-3 bg-warning-bg edge border-warning border-b-0 border-x-0"
    >
      <span aria-hidden="true" className="text-warning shrink-0">
        <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="10" cy="10" r="7" />
          <path d="M10 6.5v3.5l2.3 1.4" />
        </svg>
      </span>
      <p className="text-small text-warning">{labels.explanation}</p>
      <div className="ml-auto flex items-center gap-2 shrink-0">
        <Button
          variant="primary"
          data-testid="repropose"
          state={busy === 'repropose' ? 'loading' : 'default'}
          onClick={() => {
            void act('repropose');
          }}
        >
          {labels.repropose}
        </Button>
        <Button
          variant="secondary"
          data-testid="discard"
          state={busy === 'discard' ? 'loading' : 'default'}
          onClick={() => {
            void act('discard');
          }}
        >
          {labels.discard}
        </Button>
      </div>
      {failed ? (
        <p data-testid="expired-footer-failed" className="text-meta text-danger">
          {labels.failed}
        </p>
      ) : null}
    </div>
  );
}
