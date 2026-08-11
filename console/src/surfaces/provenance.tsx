import type { ReactNode } from 'react';

import { Link } from '@/components/action';

/**
 * Where this came from and where it went, for one crossing of the boundary.
 *
 * The half of provenance that was missing. Configuration already carries it per
 * value and an investigation attributes every claim to its source; transit did
 * not, so "this alert entered by this route, matched this rule, went to this
 * team" was a sentence nobody could complete from a screen.
 *
 * A disclosure rather than a column, because the chain is what somebody opens
 * when the answer is not obvious — and a table wide enough to hold it is a table
 * that is unreadable for the ninety per cent of rows where it is.
 *
 * The run is a link. That is the whole of the second question: from the run,
 * every finding already names the query, the origin and the instant it came
 * from, so the chain does not stop here — it hands over to something that
 * already exists.
 */

export interface ProvenanceLabels {
  readonly open: string;
  readonly source: string;
  readonly rule: string;
  readonly team: string;
  readonly run: string;
  readonly resource: string;
  readonly none: string;
}

export interface ProvenanceChain {
  readonly source: string;
  readonly instant: string;
  readonly outcome: string;
  readonly rule: string;
  readonly team: string;
  readonly run: string;
  readonly resource: string;
}

export interface ProvenanceProps {
  readonly chain: ProvenanceChain;
  readonly labels: ProvenanceLabels;
}

/** One row's chain: route, rule, team, resource, and a link to the run. */
export function Provenance({ chain, labels }: ProvenanceProps): ReactNode {
  const entries: readonly (readonly [string, string])[] = [
    [labels.source, chain.source],
    [labels.rule, chain.rule],
    [labels.team, chain.team],
    [labels.resource, chain.resource],
  ];
  const known = entries.filter(([, value]) => value !== '');
  // An arrival with no instant is no arrival: the source was enumerated from
  // the receivers this deployment serves, and the ledger had nothing for it.
  // Rendering the route's own name as a "chain" would be answering a question
  // nobody asked with the input they gave.

  return (
    <details data-testid="provenance" data-run={chain.run}>
      <summary className="text-meta text-muted">{labels.open}</summary>
      {chain.instant === '' ? (
        <span className="text-meta text-muted" data-testid="provenance-none">
          {labels.none}
        </span>
      ) : (
        <dl className="text-meta flex flex-col gap-1" data-testid="provenance-chain">
          {known.map(([label, value]) => (
            <div key={label} className="flex gap-2">
              <dt className="text-muted">{label}</dt>
              <dd className="text-strong">{value}</dd>
            </div>
          ))}
          {chain.run === '' ? null : (
            <div className="flex gap-2">
              <dt className="text-muted">{labels.run}</dt>
              <dd>
                <Link href={`/runs/${chain.run}`} data-testid="provenance-run">
                  {chain.run}
                </Link>
              </dd>
            </div>
          )}
        </dl>
      )}
    </details>
  );
}
