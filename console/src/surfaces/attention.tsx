import type { ReactNode } from 'react';

import NextLink from 'next/link';

import { AlertTriangleIcon, ArrowRightIcon } from '@/design/icons';
import { humaniseIdentifier } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { AttentionDecisionControls } from './attention-decision-controls';
import { RiskLadder } from './risk-ladder';

/**
 * "Precisa de você": the pending remediation decided inline, never a
 * navigation away.
 *
 * This used to be a general "things waiting on a person" list — approvals,
 * proposals, urgent incidents and failed runs together, capped at six rows
 * with an overflow link. The redesign narrows it to exactly what
 * `Main.dc.html` draws: the proposed-action decision itself, with the plan
 * and the reversal visible before either button is clickable. What the old
 * band also carried — a failed run, an incident nobody has picked up — has
 * no explicit new home in this feature's requirements; it is named in the
 * control file as scope this feature does not cover, not silently dropped.
 *
 * **Decided at the approval store, never through a live-run interaction.**
 * `AttentionDecisionControls` (`attention-decision-controls.tsx`) posts to
 * `/api/approval`, which addresses `POST /v1/approvals/{approval_id}
 * /decision` — the identical courier `IncidentDecisionControls`
 * (`screens/incident-decision-controls.tsx`, the incident page's own card for
 * the same entity) already uses. A proposed remediation — the mockup's own
 * example, "proposed by the alert router" — is an `ApprovalRequest` decided
 * directly at the approval store; it is not a live investigation pausing to
 * ask a question, which is the *other* mechanism (`surfaces/decision.tsx`'s
 * `DecisionControls`, addressing `/v1/interactions/{id}/approve`) exists
 * for. This band's own component, rather than reusing the incident page's,
 * because the two disagree about how the reject reason is revealed —
 * `Main.dc.html` draws Recusar as a flat control with no field open beside
 * it, where the incident page's card shows the field from the start — and
 * both go through the one courier, so neither is a second opinion about
 * which route a propose-only decision takes.
 */

/** One numbered step of a plan or its reversal. */
export interface DecisionStep {
  readonly ordinal: number;
  readonly summary: string;
}

/** One pending remediation, as this band reads it — read-only until decided. */
export interface DecisionCardData {
  readonly id: string;
  readonly title: string;
  readonly riskClass: string;
  readonly since: string;
  readonly steps: readonly DecisionStep[];
  readonly rollback: readonly DecisionStep[];
}

interface StepListProps {
  readonly testId: string;
  readonly heading: string;
  readonly steps: readonly DecisionStep[];
}

function StepList({ testId, heading, steps }: StepListProps): ReactNode {
  if (steps.length === 0) return null;
  return (
    <div data-testid={testId} className="flex flex-col gap-1 min-w-0">
      <span className="text-micro text-muted uppercase tracking-wide">{heading}</span>
      <ol className="flex flex-col gap-1 text-small list-decimal list-inside">
        {steps.map((step) => (
          <li key={step.ordinal}>{step.summary}</li>
        ))}
      </ol>
    </div>
  );
}

interface DecisionCardProps {
  readonly locale: Locale;
  readonly decision: DecisionCardData;
  readonly canDecide: boolean;
  readonly expanded: boolean;
}

/** One card: title, risk, age, plan and reversal, and — permission allowing — the controls. */
function DecisionCard({
  locale,
  decision,
  canDecide,
  expanded,
}: DecisionCardProps): ReactNode {
  const planHref = `/decisions?tab=actions&selected=${encodeURIComponent(decision.id)}`;
  return (
    <li
      data-testid="attention-decision-card"
      data-expanded={expanded ? 'true' : 'false'}
      className="edge border-warning rounded-2 bg-warning-bg px-4 py-3 flex flex-col gap-3"
    >
      <div className="flex items-start gap-3 flex-wrap">
        <span
          data-testid="attention-decision-title"
          className="text-strong flex-1 min-w-0"
        >
          {decision.title}
        </span>
        <span
          data-testid="attention-decision-age"
          className="text-meta text-muted shrink-0"
        >
          {decision.since}
        </span>
      </div>
      <div data-testid="attention-decision-risk">
        <RiskLadder
          riskClass={decision.riskClass}
          label={humaniseIdentifier(decision.riskClass)}
        />
      </div>
      {expanded ? (
        <div className="flex flex-wrap gap-4">
          <StepList
            testId="attention-decision-plan"
            heading={message(locale, 'dashboard.decisionBand.plan')}
            steps={decision.steps}
          />
          <StepList
            testId="attention-decision-rollback"
            heading={message(locale, 'dashboard.decisionBand.rollback')}
            steps={decision.rollback}
          />
        </div>
      ) : null}
      <div className="flex items-center gap-3 flex-wrap">
        {canDecide ? (
          expanded ? (
            <AttentionDecisionControls
              approvalId={decision.id}
              labels={{
                approve: message(locale, 'dashboard.decisionBand.approve'),
                reject: message(locale, 'dashboard.decisionBand.reject'),
                reason: message(locale, 'dashboard.decisionBand.reason'),
                submit: message(locale, 'dashboard.decisionBand.rejectSubmit'),
                cancel: message(locale, 'dashboard.decisionBand.cancel'),
                reasonRequired: message(
                  locale,
                  'dashboard.decisionBand.reasonRequired',
                ),
                failed: message(locale, 'dashboard.decisionBand.failed'),
              }}
            />
          ) : null
        ) : (
          <span
            data-testid="attention-decision-no-permission"
            className="text-meta text-muted"
          >
            {message(locale, 'dashboard.decisionBand.noPermission')}
          </span>
        )}
        <a
          href={planHref}
          data-testid="attention-view-plan"
          className="text-meta text-accent hover:underline ml-auto"
        >
          {message(locale, 'dashboard.decisionBand.viewPlan')}
        </a>
      </div>
    </li>
  );
}

export interface AttentionBlockProps {
  readonly locale: Locale;
  /** Pending remediations, oldest first — the caller's own sort, unchanged here. */
  readonly decisions: readonly DecisionCardData[];
  /** Whether this viewer holds the permission to decide. */
  readonly canDecide: boolean;
}

/** "Precisa de você": the oldest decision expanded, the rest compact with a count. */
export function AttentionBlock({
  locale,
  decisions,
  canDecide,
}: AttentionBlockProps): ReactNode {
  if (decisions.length === 0) {
    return (
      <section
        data-testid="attention-decision-band"
        aria-label={message(locale, 'dashboard.decisionBand.title')}
        className="edge border-border rounded-3 bg-raised px-4 py-4 flex items-center gap-2"
      >
        <p data-testid="attention-decision-empty" className="text-small text-muted">
          {message(locale, 'dashboard.decisionBand.empty')}{' '}
          <NextLink href="/decisions" className="text-accent hover:underline">
            {message(locale, 'dashboard.decisionBand.empty.action')}
          </NextLink>
        </p>
      </section>
    );
  }

  const [oldest, ...rest] = decisions;

  return (
    <section
      data-testid="attention-decision-band"
      aria-label={message(locale, 'dashboard.decisionBand.title')}
      className="flex flex-col gap-2"
    >
      <ul className="flex flex-col gap-2">
        {oldest === undefined ? null : (
          <DecisionCard
            locale={locale}
            decision={oldest}
            canDecide={canDecide}
            expanded
          />
        )}
        {rest.map((decision) => (
          <DecisionCard
            key={decision.id}
            locale={locale}
            decision={decision}
            canDecide={canDecide}
            expanded={false}
          />
        ))}
      </ul>
      {rest.length === 0 ? null : (
        <p className="text-meta text-muted flex items-center gap-2">
          <AlertTriangleIcon />
          {message(locale, 'dashboard.decisionBand.more', {
            count: String(rest.length),
          })}
          <ArrowRightIcon />
        </p>
      )}
    </section>
  );
}
