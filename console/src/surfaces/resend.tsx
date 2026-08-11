'use client';

import { useState, type ReactNode } from 'react';

/**
 * Send a report that did not arrive again.
 *
 * A report that did not arrive is worse than one that never existed, because
 * somebody is waiting for it. So a failed delivery is a visible state with a
 * control on it rather than a row an operator can only read — and the control
 * says what happened, including when the second attempt failed too.
 *
 * The button does not disappear on success. An operator who re-sent something
 * wants to see that it went, and a control that vanished would leave them
 * wondering whether they had clicked it.
 */

/** Where a re-send is asked. The console's own process, forwarding once. */
export const RESEND_ENDPOINT = '/api/resend';

export interface ResendLabels {
  readonly resend: string;
  readonly resending: string;
  readonly delivered: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface ResendProps {
  readonly deliveryId: string;
  readonly labels: ResendLabels;
}

/** One control, for one failed outbound delivery. */
export function Resend({ deliveryId, labels }: ResendProps): ReactNode {
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState('');

  async function send(): Promise<void> {
    setBusy(true);
    setOutcome('');
    let response: Response;
    try {
      response = await fetch(RESEND_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ deliveryId }),
      });
    } catch {
      setBusy(false);
      setOutcome(labels.unreachable);
      return;
    }
    const resent: unknown = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setOutcome(labels.failed);
      return;
    }
    const answered = String(Reflect.get(Object(resent), 'outcome') ?? '');
    setOutcome(answered === 'delivered' ? labels.delivered : labels.failed);
  }

  return (
    <span
      className="flex items-center gap-2"
      data-testid="resend"
      data-delivery={deliveryId}
    >
      <button
        type="button"
        className="text-meta text-strong underline"
        data-testid="resend-action"
        disabled={busy}
        onClick={() => {
          void send();
        }}
      >
        {busy ? labels.resending : labels.resend}
      </button>
      {outcome === '' ? null : (
        <span className="text-meta text-muted" data-testid="resend-outcome">
          {outcome}
        </span>
      )}
    </span>
  );
}
