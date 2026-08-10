'use client';

import { useState, type ReactNode } from 'react';

/**
 * The credential an operator pastes into their alert router, shown exactly once.
 *
 * Three properties, and each one is a decision rather than a convenience.
 *
 * **It is asked for, never pre-issued.** A deployment that minted a delivery
 * token on first boot would be a deployment with a live credential nobody chose
 * to create, sitting in a database until somebody found it.
 *
 * **It is shown once and never read back.** The store holds a hash; there is no
 * route that returns a secret, so a page reload is a page with nothing on it.
 * That is why the value lives in component state and nowhere else — not in the
 * URL, not in storage, not in a server-rendered attribute.
 *
 * **It is scoped to one permission.** The panel asks for the delivery
 * permission the deployment named, so what ends up in somebody else's
 * configuration file can raise an alert and read nothing at all.
 */

/** Where the token is minted. The console's own process, forwarding once. */
export const DELIVERY_TOKEN_ENDPOINT = '/api/delivery-token';

export interface DeliveryTokenLabels {
  readonly issue: string;
  readonly issuing: string;
  readonly shownOnce: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface DeliveryTokenProps {
  /** What the deployment said a delivery credential must be scoped to. */
  readonly permission: string;
  readonly labels: DeliveryTokenLabels;
}

/** A button that mints one delivery token, and the one place its value appears. */
export function DeliveryToken({ permission, labels }: DeliveryTokenProps): ReactNode {
  const [secret, setSecret] = useState('');
  const [issuing, setIssuing] = useState(false);
  const [failure, setFailure] = useState('');

  async function issue(): Promise<void> {
    setIssuing(true);
    setFailure('');
    let answer: Response;
    try {
      answer = await fetch(DELIVERY_TOKEN_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ permission }),
      });
    } catch {
      setIssuing(false);
      setFailure(labels.unreachable);
      return;
    }
    const issued: unknown = await answer.json().catch(() => ({}));
    setIssuing(false);
    if (!answer.ok) {
      setFailure(labels.failed);
      return;
    }
    const value: unknown = Reflect.get(Object(issued), 'secret');
    setSecret(typeof value === 'string' ? value : '');
  }

  return (
    <div className="flex flex-col gap-2" data-testid="delivery-token">
      <button
        type="button"
        className="text-small text-strong self-start underline"
        disabled={issuing}
        onClick={() => {
          void issue();
        }}
      >
        {issuing ? labels.issuing : labels.issue}
      </button>
      {secret === '' ? null : (
        <div className="flex flex-col gap-1">
          <code className="text-small break-all" data-testid="delivery-secret">
            {secret}
          </code>
          <span className="text-meta text-warning">{labels.shownOnce}</span>
        </div>
      )}
      {failure === '' ? null : (
        <span className="text-meta text-danger" data-testid="delivery-token-failure">
          {failure}
        </span>
      )}
    </div>
  );
}
