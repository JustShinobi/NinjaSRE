'use client';

import { useState, type ReactNode } from 'react';

import { Button } from '@/components/action';
import { StatusChip } from '@/components/status';
import type { Locale } from '@/i18n/messages';
import {
  CredentialField,
  type CredentialFieldSpec,
  type CredentialLabels,
} from './credential';
import { VerifyStep, type VerifyStepLabels } from './first-run/verify';

/**
 * One integration, collapsed to its state until somebody asks for more.
 *
 * Eighty-five of these on one screen is the whole reason this collapses: an
 * operator with three real integrations should not scroll past eighty-two
 * open forms with nothing behind them to find the three that matter. What is
 * visible without expanding anything is exactly the state a card has to be
 * legible for — absent, stored, verified, failing — read straight off
 * `health`, which distinguishes all four (`platform/credentials/health.py`'s
 * vault read joined with the verification ledger, at
 * `integrations/_catalogue/discovery.py`'s `catalogue`).
 *
 * The credential form and the "check it for real" control both live behind
 * the same toggle: a form with nothing to test is half a card, and a test
 * with no way to fix what it finds is the other half.
 */

export interface IntegrationCardLabels {
  readonly expand: string;
  readonly collapse: string;
  /** One sentence per `health` word this card can show, keyed by the raw value. */
  readonly explanation: Readonly<Record<string, string>>;
  readonly credential: CredentialLabels;
  readonly verify: VerifyStepLabels;
}

export interface IntegrationCardProps {
  readonly locale: Locale;
  readonly name: string;
  /** What a person calls this vendor. Shown instead of `name`, which stays for technical attributes. */
  readonly displayName: string;
  /** `unconfigured` | `unknown` | `healthy` | `degraded`, verbatim from the API. */
  readonly health: string;
  readonly healthDetail: string;
  readonly fields: readonly CredentialFieldSpec[];
  readonly labels: IntegrationCardLabels;
}

/** A collapsed card: name, state, and a legend — the form only on request. */
export function IntegrationCard({
  locale,
  name,
  displayName,
  health,
  healthDetail,
  fields,
  labels,
}: IntegrationCardProps): ReactNode {
  const [expanded, setExpanded] = useState(false);
  const explanation = labels.explanation[health];

  return (
    <li
      data-testid="integration"
      data-integration={name}
      data-state={health}
      className="flex flex-col gap-2 rounded-3 edge border-border p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-strong">{displayName}</span>
        <StatusChip locale={locale} status={health} />
        <Button
          variant="quiet"
          data-testid="integration-toggle"
          aria-expanded={expanded}
          onClick={() => {
            setExpanded(!expanded);
          }}
        >
          {expanded ? labels.collapse : labels.expand}
        </Button>
      </div>
      {explanation === undefined ? null : (
        <p className="text-meta text-muted" data-testid="integration-state-explanation">
          {explanation}
        </p>
      )}
      {healthDetail === '' ? null : (
        <p className="text-meta text-muted">{healthDetail}</p>
      )}
      {expanded ? (
        <div className="flex flex-col gap-3 pt-2">
          <VerifyStep
            locale={locale}
            things={[{ kind: 'integration', name, displayName, readiness: health }]}
            labels={labels.verify}
          />
          <CredentialField
            integration={name}
            fields={fields}
            labels={labels.credential}
          />
        </div>
      ) : null}
    </li>
  );
}
