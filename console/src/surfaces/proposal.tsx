import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { ShieldIcon } from '@/design/icons';

/**
 * A change waiting on a person, with everything needed to decide it.
 *
 * **Eight fields, always, in this order**, and the order is not a layout
 * preference. It is the order somebody decides in: what is being touched, what
 * state it is in now, what would change, what each item protects, who else is
 * affected, whether it can be undone, how it will be checked, and what the
 * deployment would have done unattended. A card that dropped a field because the
 * payload had nothing for it would be a card whose shape depends on the data,
 * and a reader would learn to scan for the fields rather than read down them.
 *
 * So a field with nothing behind it says so. "Not recorded" is a fact about the
 * proposal; an absent row is a fact about the renderer, and only one of those is
 * information.
 */

export const PROPOSAL_FIELDS = [
  'target',
  'current',
  'change',
  'protects',
  'blast',
  'rollback',
  'verification',
  'autonomy',
] as const;

export type ProposalField = (typeof PROPOSAL_FIELDS)[number];

/** One field's label and its value, already phrased. */
export interface ProposalRow {
  readonly field: ProposalField;
  readonly label: string;
  readonly value: string;
  /** Rendered under the value, one line each. Used by "what each protects". */
  readonly items?: readonly { readonly badge: string; readonly text: string }[];
  /** Whether the value is the kind that has to be read before deciding. */
  readonly grave?: boolean;
}

export interface ProposalCardProps {
  readonly heading: string;
  /** "Risk 4 of 5", already phrased. */
  readonly risk: string;
  readonly rows: readonly ProposalRow[];
  /** The decision controls, which are absent for a viewer who may not decide. */
  readonly decision?: ReactNode;
}

/** The proposal card: eight fields, then the decision. */
export function ProposalCard({
  heading,
  risk,
  rows,
  decision,
}: ProposalCardProps): ReactNode {
  return (
    <section
      data-testid="proposal"
      aria-label={heading}
      className="rounded-3 edge border-danger bg-raised"
    >
      <header className="flex items-center gap-2 px-4 py-3 edge border-border border-t-0 border-x-0">
        <span className="text-danger" aria-hidden="true">
          <ShieldIcon />
        </span>
        <h3 className="text-section">{heading}</h3>
        <span className="ml-auto text-micro uppercase edge border-danger text-danger rounded-1 px-2">
          {risk}
        </span>
      </header>
      <dl className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-4">
        {rows.map((row) => (
          <div
            key={row.field}
            className="contents"
            data-testid="proposal-row"
            data-field={row.field}
          >
            <dt className="text-meta text-muted">{row.label}</dt>
            <dd className="text-small sm:col-span-3 min-w-0">
              <span className={row.grave === true ? 'text-danger' : ''}>
                {row.value}
              </span>
              {row.items === undefined ? null : (
                <ul className="flex flex-col gap-1 mt-1">
                  {row.items.map((item) => (
                    <li key={item.text} className="flex items-start gap-2 min-w-0">
                      <Badge status={item.badge} />
                      <span className="min-w-0 break-all">{item.text}</span>
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
        ))}
      </dl>
      {decision === undefined ? null : (
        <footer className="px-4 py-3 edge border-border border-b-0 border-x-0">
          {decision}
        </footer>
      )}
    </section>
  );
}
