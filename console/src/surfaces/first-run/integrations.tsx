'use client';

import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';

import { Input } from '@/components/form';
import {
  CredentialField,
  type CredentialFieldSpec,
  type CredentialLabels,
} from '../credential';

/**
 * Connecting vendors, one at a time, where failing at one does not abandon the
 * rest.
 *
 * That rule is the CLI's — its `setup_many` continues after a failure and
 * reports at the end — and the console may not be stricter than the CLI about
 * the same operation. So each integration here writes on its own, keeps its own
 * outcome, and the summary at the bottom is what was collected rather than
 * where the loop stopped. An operator who mistyped one token has still
 * connected the other three.
 *
 * Nothing is required. A deployment with a provider and no integration still
 * investigates — from what it is told rather than from what it can go and look
 * at — and forcing a choice here is exactly how a guided setup gets abandoned
 * at step four.
 *
 * **The order is the deployment's, not this file's.** Discovery has already been
 * through the cluster, so the deployment knows which of these vendors is running
 * on it and where — and serves the catalogue with those first. Re-sorting here
 * would be the console deriving relevance a second time, and two surfaces
 * deriving it separately is how one offers Prometheus first while the other
 * buries it. The search filters; it never reorders.
 */

/** One vendor, and the form it declares. */
export interface IntegrationOffer {
  readonly name: string;
  readonly displayName: string;
  readonly summary: string;
  readonly category: string;
  /** The credential schema, when the deployment serves one for this vendor. */
  readonly fields: readonly CredentialFieldSpec[];
  /** Whether this deployment already holds a credential for it. */
  readonly configured: boolean;
  /**
   * Where this deployment's own estate says this vendor is already running.
   *
   * Absent for everything the estate says nothing about, which is most of the
   * catalogue. Present, it is the answer to the only hard question on this
   * screen: which of fifty-seven containers is the metric store.
   */
  readonly suggested?:
    { readonly address: string; readonly because: string } | undefined;
}

export interface IntegrationsStepLabels {
  readonly search: string;
  readonly none: string;
  readonly connected: string;
  readonly notConnected: string;
  readonly optional: string;
  readonly summary: string;
  readonly summaryNone: string;
  readonly failed: string;
  readonly foundHere: string;
  readonly credential: CredentialLabels;
}

export interface IntegrationsStepProps {
  readonly offers: readonly IntegrationOffer[];
  readonly labels: IntegrationsStepLabels;
}

/** The catalogue, searchable, with a schema-driven form behind each entry. */
export function IntegrationsStep({ offers, labels }: IntegrationsStepProps): ReactNode {
  const [query, setQuery] = useState('');
  const [stored, setStored] = useState<readonly string[]>([]);

  const matching = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === '') return offers;
    return offers.filter((offer) =>
      `${offer.name} ${offer.displayName} ${offer.summary} ${offer.category}`
        .toLowerCase()
        .includes(needle),
    );
  }, [offers, query]);

  return (
    <div data-testid="integrations-step" className="flex flex-col gap-4">
      <p className="text-small text-muted">{labels.optional}</p>

      <Input
        label={labels.search}
        name="integration-search"
        type="search"
        value={query}
        onValueChange={setQuery}
      />

      {matching.length === 0 ? (
        <p className="text-meta text-muted" data-testid="no-integration-matches">
          {labels.none}
        </p>
      ) : (
        <ul className="flex flex-col gap-4">
          {matching.map((offer) => (
            <li
              key={offer.name}
              data-testid="integration-offer"
              data-integration={offer.name}
              className="flex flex-col gap-2 rounded-3 edge border-border p-4"
            >
              <p className="text-strong">{offer.displayName}</p>
              <p className="text-meta text-muted">{offer.summary}</p>
              {offer.suggested === undefined ? null : (
                <p
                  className="text-meta text-accent"
                  data-testid="integration-suggested"
                >
                  {labels.foundHere} {offer.suggested.address}
                </p>
              )}
              <p className="text-meta text-muted" data-testid="integration-state">
                {offer.configured || stored.includes(offer.name)
                  ? labels.connected
                  : labels.notConnected}
              </p>
              <CredentialField
                integration={offer.name}
                fields={offer.fields}
                labels={labels.credential}
                onStored={(name) => {
                  // Collected rather than acted on. One vendor's write does not
                  // move the screen, because the next thing an operator does is
                  // usually the next vendor.
                  setStored((held) => (held.includes(name) ? held : [...held, name]));
                }}
              />
            </li>
          ))}
        </ul>
      )}

      <p className="text-meta text-muted" data-testid="integrations-summary">
        {stored.length === 0
          ? labels.summaryNone
          : labels.summary.replace('{names}', stored.join(', '))}
      </p>
    </div>
  );
}
