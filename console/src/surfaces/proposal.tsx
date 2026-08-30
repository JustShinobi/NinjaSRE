import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { AlertTriangleIcon } from '@/design/icons';
import { Link } from '@/components/action';
import type { ExpiredFooterProps } from './expired-footer';
import { ExpiredFooterControls } from './expired-footer';

/**
 * The decision card: one action, by field, in the artboard's own anatomy
 * (`design/padrao-2026-08/Decisions.dc.html`).
 *
 * **Six named sections, always**, because that is the order a reviewer reads
 * in: what will happen, how it undoes, why, what evidence supports it, what
 * it reaches, and how autonomous the write is. A section with nothing behind
 * it says so — "not recorded" is a fact about the document, and a section
 * that silently disappeared would be a fact about the renderer instead.
 *
 * **The two live decide-in-place paths are composed exactly as `approvals.tsx`
 * builds them.** This component never decides which of `DecisionControls` or
 * `IncidentDecisionControls` to use — that stays `decisionFor`'s call, in the
 * screen — it only has a slot for whichever `ReactNode` arrives.
 */

export interface ActionStep {
  readonly ordinal: number;
  readonly summary: string;
  readonly capability: string;
}

export interface EvidenceItem {
  readonly summary: string;
  readonly href: string;
}

export interface DecisionRisk {
  readonly class: string;
  readonly score: number;
  readonly scale: number;
}

export interface DecisionOutcome {
  readonly verdict: string;
  readonly decidedBy: string;
  readonly relativeTime: string;
  readonly appliedAndVerified: boolean;
}

export const DECISION_STATES = ['pending', 'expired', 'approved', 'rejected', 'discarded'] as const;

export type DecisionState = (typeof DECISION_STATES)[number];

export interface DecisionCardLabels {
  readonly steps: string;
  readonly rollback: string;
  readonly noRollback: string;
  readonly why: string;
  readonly evidence: string;
  readonly evidenceLink: string;
  readonly blastRadius: string;
  readonly rawPayload: string;
  readonly notRecorded: string;
  readonly risk: string;
  readonly outcome: string;
}

export interface DecisionCardProps {
  readonly approvalId: string;
  readonly state: DecisionState;
  readonly title: string;
  readonly requester: string;
  readonly originHref?: string;
  readonly originLabel?: string;
  readonly category: string;
  readonly risk: DecisionRisk;
  readonly steps: readonly ActionStep[];
  readonly rollback: readonly ActionStep[];
  readonly reversible: boolean;
  readonly why: string;
  readonly evidence: readonly EvidenceItem[];
  readonly blastRadiusText: string;
  readonly autonomyText: string;
  readonly rawPayload: string;
  readonly rawPayloadLabel: string;
  /** Shown as the lone numbered step when `steps` is empty but a summary exists. */
  readonly summaryFallback?: string;
  /** Absent for a viewer who may not decide. */
  readonly decision?: ReactNode;
  /** Present only when `state === 'expired'`. */
  readonly expiredFooter?: ExpiredFooterProps;
  /** Present only when the decision has already been decided. */
  readonly outcome?: DecisionOutcome;
}

function Section({
  name,
  label,
  danger = false,
  children,
}: {
  readonly name: string;
  readonly label: string;
  readonly danger?: boolean;
  readonly children: ReactNode;
}): ReactNode {
  return (
    <div
      data-testid="decision-section"
      data-section={name}
      data-danger={danger ? 'true' : undefined}
      className="flex flex-col gap-2"
    >
      <span className="text-micro font-semibold tracking-wide uppercase text-muted">{label}</span>
      {children}
    </div>
  );
}

function Steps({
  items,
  summaryFallback,
  notRecorded,
  danger = false,
}: {
  readonly items: readonly ActionStep[];
  readonly summaryFallback?: string | undefined;
  readonly notRecorded: string;
  readonly danger?: boolean;
}): ReactNode {
  const shown =
    items.length > 0
      ? items
      : summaryFallback !== undefined && summaryFallback !== ''
        ? [{ ordinal: 1, summary: summaryFallback, capability: '' }]
        : [];

  if (shown.length === 0) {
    return <p className={danger ? 'text-small text-danger' : 'text-small text-muted'}>{notRecorded}</p>;
  }

  return (
    <ol className="flex flex-col gap-2">
      {shown.map((step) => (
        <li key={step.ordinal} data-testid="decision-step" className="flex gap-2 items-start">
          <span
            data-testid="step-ordinal"
            className={
              danger
                ? 'flex-shrink-0 mt-px flex items-center justify-center icon-inline rounded-full bg-danger-bg text-danger edge border-danger text-micro font-semibold'
                : 'flex-shrink-0 mt-px flex items-center justify-center icon-inline rounded-full bg-success-bg text-success edge border-success text-micro font-semibold'
            }
          >
            {step.ordinal}
          </span>
          <span className="text-small">
            {step.summary}
            {step.capability === '' ? null : (
              <span className="ml-2 text-micro text-muted font-mono">({step.capability})</span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

function RollbackSteps({
  items,
  danger,
  notRecorded,
}: {
  readonly items: readonly ActionStep[];
  readonly danger: boolean;
  readonly notRecorded: string;
}): ReactNode {
  if (items.length === 0) {
    return (
      <p data-testid="no-rollback" className="text-small text-danger">
        {notRecorded}
      </p>
    );
  }
  return (
    <ol className="flex flex-col gap-2">
      {items.map((step) => (
        <li key={step.ordinal} data-testid="rollback-step" className="flex gap-2 items-start">
          <span
            data-testid="step-ordinal"
            className={
              danger
                ? 'flex-shrink-0 mt-px flex items-center justify-center icon-inline rounded-full bg-danger-bg text-danger edge border-danger text-micro font-semibold'
                : 'flex-shrink-0 mt-px flex items-center justify-center icon-inline rounded-full bg-success-bg text-success edge border-success text-micro font-semibold'
            }
          >
            {step.ordinal}
          </span>
          <span className="text-small">
            {step.summary}
            {step.capability === '' ? null : (
              <span className="ml-2 text-micro text-muted font-mono">({step.capability})</span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** The risk gauge: `scale` segments, `score` of them filled. */
function RiskGauge({ risk, label }: { readonly risk: DecisionRisk; readonly label: string }): ReactNode {
  const segments = Array.from({ length: risk.scale }, (_, index) => index < risk.score);
  return (
    <div
      data-testid="decision-risk"
      data-risk-score={risk.score}
      data-risk-scale={risk.scale}
      className="flex flex-col items-end gap-1"
    >
      <span className="text-micro text-muted">{label}</span>
      <div className="flex gap-1">
        {segments.map((filled, index) => (
          <span
            key={index}
            data-testid="risk-segment"
            data-filled={filled ? 'true' : 'false'}
            className={
              filled ? 'w-4 h-1 rounded-1 bg-warning' : 'w-4 h-1 rounded-1 bg-sunken'
            }
          />
        ))}
      </div>
    </div>
  );
}

/** What was decided, in place of any control — a decision does not decide twice. */
function Outcome({ outcome, label }: { readonly outcome: DecisionOutcome; readonly label: string }): ReactNode {
  return (
    <footer
      data-testid="decision-outcome"
      className="flex items-center gap-2 px-5 py-3 rounded-b-3 edge border-border border-b-0 border-x-0"
    >
      <Badge status={outcome.verdict} />
      <span className="text-small text-muted">
        {label} — {outcome.decidedBy}
        {outcome.appliedAndVerified ? ', applied and verified' : ''} · {outcome.relativeTime}
      </span>
    </footer>
  );
}

const DEFAULT_LABELS: DecisionCardLabels = {
  steps: 'What will happen',
  rollback: 'If it goes wrong — rollback',
  noRollback: 'No rollback recorded — this action cannot be undone.',
  why: 'Why',
  evidence: 'Evidence behind this',
  evidenceLink: 'view',
  blastRadius: 'Blast radius',
  rawPayload: 'raw action payload',
  notRecorded: 'Not recorded.',
  risk: 'Risk',
  outcome: 'Decided',
};

export function DecisionCard({
  approvalId,
  state,
  title,
  requester,
  originHref,
  originLabel,
  category,
  risk,
  steps,
  rollback,
  reversible,
  why,
  evidence,
  blastRadiusText,
  autonomyText,
  rawPayload,
  rawPayloadLabel,
  summaryFallback,
  decision,
  expiredFooter,
  outcome,
}: DecisionCardProps): ReactNode {
  const labels = DEFAULT_LABELS;
  const rollbackDanger = !reversible;

  return (
    <section
      data-testid="decision-card"
      data-approval={approvalId}
      data-state={state}
      aria-label={title}
      className={
        state === 'expired'
          ? 'rounded-3 edge border-warning bg-raised'
          : 'rounded-3 edge border-border bg-raised'
      }
    >
      <header className="flex items-start gap-3 px-5 py-4 edge border-border border-t-0 border-x-0">
        <span aria-hidden="true" className="text-warning shrink-0 mt-1">
          <AlertTriangleIcon />
        </span>
        <div className="flex flex-col gap-1 min-w-0">
          <h3 data-testid="decision-title" className="text-section">
            {title}
          </h3>
          <p data-testid="decision-meta" className="text-meta text-muted">
            {requester}
            {originHref === undefined || originLabel === undefined || originLabel === '' ? null : (
              <>
                {' · '}
                <Link href={originHref}>{originLabel}</Link>
              </>
            )}
            {' · '}
            {category}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3 shrink-0">
          <RiskGauge risk={risk} label={labels.risk} />
          <span data-testid="decision-state">
            <Badge status={state} />
          </span>
        </div>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-0">
        <div className="flex flex-col gap-4 px-5 py-4 edge border-border border-y-0 border-l-0">
          <Section name="steps" label={labels.steps}>
            <Steps items={steps} summaryFallback={summaryFallback} notRecorded={labels.notRecorded} />
          </Section>
          <Section name="rollback" label={labels.rollback} danger={rollbackDanger}>
            <RollbackSteps items={rollback} danger={rollbackDanger} notRecorded={labels.noRollback} />
          </Section>
          <details data-testid="raw-payload">
            <summary className="text-meta text-muted cursor-pointer">{rawPayloadLabel}</summary>
            <pre className="mt-2 text-micro text-muted bg-sunken edge border-border rounded-2 p-2 overflow-x-auto font-mono">
              {rawPayload}
            </pre>
          </details>
        </div>
        <div className="flex flex-col gap-4 px-5 py-4">
          <Section name="why" label={labels.why}>
            <p className="text-small">{why === '' ? labels.notRecorded : why}</p>
          </Section>
          <Section name="evidence" label={labels.evidence}>
            {evidence.length === 0 ? (
              <p className="text-small text-muted">{labels.notRecorded}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {evidence.map((item) => (
                  <li
                    key={item.summary}
                    data-testid="evidence-item"
                    className="flex items-center gap-2"
                  >
                    <span className="w-2 h-2 rounded-full bg-success shrink-0" aria-hidden="true" />
                    <span className="text-meta min-w-0">{item.summary}</span>
                    <a
                      data-testid="evidence-link"
                      href={item.href}
                      className="ml-auto text-micro text-accent shrink-0 underline"
                    >
                      {labels.evidenceLink}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section name="blast-radius" label={labels.blastRadius}>
            <p className="text-small">{blastRadiusText}</p>
          </Section>
          <div
            data-testid="decision-section"
            data-section="autonomy"
            className="flex items-center gap-2 bg-success-bg edge border-success rounded-2 px-3 py-2"
          >
            <span className="text-success text-small">{autonomyText}</span>
          </div>
        </div>
      </div>

      {state === 'expired' && expiredFooter !== undefined ? (
        <ExpiredFooterControls {...expiredFooter} />
      ) : outcome !== undefined ? (
        <Outcome outcome={outcome} label={labels.outcome} />
      ) : decision === undefined ? null : (
        <footer data-testid="decision-controls-footer" className="px-5 py-4 edge border-border border-b-0 border-x-0">
          {decision}
        </footer>
      )}
    </section>
  );
}
