import type { ReactNode } from 'react';

import { Breadcrumb } from '@/components/navigation';
import { ResolvedChip } from '@/components/status';
import type { Shape } from '@/design/status';
import { statusPresentation } from '@/design/status';
import type { SemanticRole } from '@/design/tokens';
import { formatCurrency, formatDuration, timestamp } from '@/i18n/format';
import type { MessageKey } from '@/i18n/en';
import { message } from '@/i18n/messages';
import { areaFor, trailFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { IncidentDecisionControls } from './incident-decision-controls';
import { UNPLACED, criticalityOf, zoneOf } from './resources-view';

/**
 * One incident: what arrived, what was reasoned about it, what was found, what
 * was concluded, what was delivered — and, when a remediation is on the table,
 * what is proposed and what it would reach.
 *
 * The mockup this screen answers to draws two columns: the investigation on
 * the left, as a timeline that reads top to bottom in the order an
 * investigation actually produces it; the proposed action and the evidence
 * trail on the right, because a decision and the receipt for it belong beside
 * each other rather than beneath a scroll.
 *
 * Every card here fails alone. An incident with no investigation attached
 * names that absence and the setup step that resolves it — never a blank
 * card — because "this deployment cannot investigate yet" and "this
 * investigation found nothing" are opposite facts and must not render the
 * same way.
 */

const CURRENCY = 'USD';

/** The five reasoning kinds `TimelineKind` carries, mapped to the short,
 * stable name this screen's own test hooks use — see `data-kind` below. */
const REASONING_KIND: Readonly<Record<string, string>> = {
  alert_received: 'receipt',
  hypotheses_drawn: 'hypotheses',
  evidence: 'evidence',
  diagnosis: 'diagnosis',
  report_delivered: 'delivery',
};

const STEP_HEADING: Readonly<Record<string, MessageKey>> = {
  receipt: 'incident.investigation.step.receipt',
  hypotheses: 'incident.investigation.step.hypotheses',
  evidence: 'incident.investigation.step.evidence',
  diagnosis: 'incident.investigation.step.diagnosis',
  delivery: 'incident.investigation.step.delivery',
};

const INCIDENT_STATE_LABEL: Readonly<Record<string, MessageKey>> = {
  open: 'incident.chip.state.open',
  investigating: 'incident.chip.state.investigating',
  awaiting_human: 'incident.chip.state.awaitingHuman',
  remediating: 'incident.chip.state.remediating',
  resolved: 'incident.chip.state.resolved',
  suppressed: 'incident.chip.state.suppressed',
  closed_without_action: 'incident.chip.state.closedWithoutAction',
};

const ORIGIN_LABEL: Readonly<Record<string, MessageKey>> = {
  alert: 'incident.origin.alert',
  detector: 'incident.origin.detector',
  human: 'incident.origin.human',
};

const DECISION_STATE_LABEL: Readonly<Record<string, MessageKey>> = {
  pending: 'incident.proposedAction.state.pending',
  approved: 'incident.proposedAction.state.approved',
  rejected: 'incident.proposedAction.state.rejected',
  expired: 'incident.proposedAction.state.expired',
};

/** `record.name` when it is a finite number, and `null` — never a fabricated
 * zero — when it is missing or not a number. */
function numberOrNull(record: unknown, name: string): number | null {
  const found = field(record, name);
  return typeof found === 'number' && Number.isFinite(found) ? found : null;
}

/** Every non-empty piece of `text`, split on `separator` and trimmed. */
function splitNonEmpty(source: string, separator: string): readonly string[] {
  return source
    .split(separator)
    .map((part) => part.trim())
    .filter((part) => part !== '');
}

export async function IncidentDetailScreen(
  context: SurfaceContext,
  incidentId: string,
): Promise<ReactNode> {
  const { credential, locale, now, zone } = context;
  const init = authorised(credential);
  const none = message(locale, 'surface.none');

  const detail = await panelRead('/v1/incidents/{incident_id}', () =>
    read('/v1/incidents/{incident_id}', {
      ...init,
      params: { incident_id: incidentId },
    }),
  );
  const body = dataOf(detail);
  const incident = field(body, 'incident');
  const timeline = list(body, 'timeline');
  const investigation = field(body, 'investigation');
  const hasInvestigation = investigation !== null && investigation !== undefined;
  const runId = text(incident, 'run_id');
  const subjects = list(incident, 'subjects');
  const subject = typeof subjects[0] === 'string' ? subjects[0] : '';

  const resource = await panelRead<unknown>('/v1/estate/resources/{resource_id}', () =>
    subject === ''
      ? Promise.resolve({})
      : read('/v1/estate/resources/{resource_id}', {
          ...init,
          params: { resource_id: subject },
        }),
  );
  const subjectRecord = field(dataOf(resource), 'resource');

  const approvals = await panelRead<unknown>('/v1/approvals', () =>
    runId === ''
      ? Promise.resolve({ approvals: [] })
      : read('/v1/approvals', {
          ...init,
          query: `?run_id=${encodeURIComponent(runId)}`,
        }),
  );
  const [proposal] = list(dataOf(approvals), 'approvals');

  // --- The five reasoning steps, in the order they happened -------------------
  const steps = timeline
    .map((entry) => ({ entry, kind: REASONING_KIND[text(entry, 'kind')] ?? '' }))
    .filter((row) => row.kind !== '');
  const hasReportDelivered = steps.some((row) => row.kind === 'delivery');
  // A diagnosis is the one reasoning step Article I lets a remediation stand
  // on. Without one, whatever is in the store is a hypothesis at best — and
  // proposing a remediation over that is the one outcome this page must never
  // render, whatever a pending approval happens to say (see below).
  const hasDiagnosis = steps.some((row) => row.kind === 'diagnosis');

  const stepCount = hasInvestigation ? numberOrNull(investigation, 'step_count') : null;
  const durationMs = hasInvestigation
    ? numberOrNull(investigation, 'duration_ms')
    : null;
  const cost = hasInvestigation ? numberOrNull(investigation, 'cost') : null;

  // --- Header: trail, title, the two chips -------------------------------------
  const title = text(incident, 'title') || incidentId;
  const trail = trailFor(areaFor('incidents'), [{ label: title }]);

  const incidentState = text(incident, 'state');
  const incidentPresented = statusPresentation(incidentState);
  const incidentStateLabel = message(
    locale,
    INCIDENT_STATE_LABEL[incidentState] ?? 'incident.chip.state.open',
  );

  const investigationChip: { role: SemanticRole; shape: Shape; label: string } =
    !hasInvestigation
      ? {
          role: 'neutral',
          shape: 'dash',
          label: message(locale, 'incident.chip.investigation.none'),
        }
      : hasReportDelivered
        ? {
            role: 'success',
            shape: 'filled-circle',
            label: message(locale, 'incident.chip.investigation.finished'),
          }
        : {
            role: 'info',
            shape: 'rotated-square',
            label: message(locale, 'incident.chip.investigation.running'),
          };

  // --- Subtitle: rule, source, instant, zone, host -----------------------------
  const rule = text(incident, 'detector');
  const source = message(
    locale,
    ORIGIN_LABEL[text(incident, 'origin')] ?? 'incident.origin.detector',
  );
  const opened = timestamp(locale, text(incident, 'opened_at'), now, zone);
  const subjectZone = zoneOf(subjectRecord);
  const zoneText =
    subjectZone === UNPLACED ? message(locale, 'resources.zone.unplaced') : subjectZone;
  const subjectKind = text(subjectRecord, 'kind');
  const subjectName = text(subjectRecord, 'display_name') || subject;
  const hostText = subjectKind === '' ? subjectName : `${subjectKind} ${subjectName}`;

  // --- Proposed action: what is on the table, its reach, and the posture ------
  // A proposal that exists in the store is not enough to show the card: an
  // approval raised over a diagnosis that never solidified is exactly the
  // outcome Article I forbids (see `hasDiagnosis` above), so the card treats
  // that combination the same as no proposal at all.
  const proposalId = text(proposal, 'approval_id');
  const hasProposal = proposal !== undefined && proposalId !== '' && hasDiagnosis;
  const decisionState = text(proposal, 'state');
  const decisionLabel = message(
    locale,
    DECISION_STATE_LABEL[decisionState] ?? 'incident.proposedAction.state.pending',
  );
  const actionSentence = text(proposal, 'summary');
  // The action's own blast radius — how many resources the topology graph
  // says depend on the target, not how many subjects this incident carries,
  // a different number answering a different question. `None` when nothing
  // has computed one for this request yet: never a fabricated count.
  const radiusResourceCount = numberOrNull(proposal, 'blast_radius_count');
  const radiusCriticality = criticalityOf(subjectRecord);
  const radiusCriticalityText =
    radiusCriticality === ''
      ? message(locale, 'resources.criticality.ungraded')
      : radiusCriticality;

  return (
    <>
      <div data-testid="page-header" data-area={areaFor('incidents').id}>
        <div data-testid="incident-trail">
          <Breadcrumb
            label={message(locale, 'breadcrumb.label')}
            trail={trail.map((crumb) => ({
              label: crumb.translate ? message(locale, crumb.label) : crumb.label,
              ...(crumb.href === undefined ? {} : { href: crumb.href }),
            }))}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h1 data-testid="incident-title" className="text-title">
            {title}
          </h1>
          <ResolvedChip
            testId="incident-chip"
            role={incidentPresented.role}
            shape={incidentPresented.shape}
            label={incidentStateLabel}
          />
          <ResolvedChip
            testId="incident-chip"
            role={investigationChip.role}
            shape={investigationChip.shape}
            label={investigationChip.label}
          />
        </div>
        <p data-testid="incident-subtitle" className="text-meta text-muted mb-5">
          <span data-testid="subtitle-rule">{rule === '' ? none : rule}</span>
          {' · '}
          <span data-testid="subtitle-source">{source}</span>
          {' · '}
          <span data-testid="subtitle-instant">
            {message(locale, 'incident.subtitle.started', { when: opened.relative })}
          </span>
          {' · '}
          <span data-testid="subtitle-zone">
            {message(locale, 'incident.subtitle.zone', { zone: zoneText })}
          </span>
          {' · '}
          <span data-testid="subtitle-host">{hostText === '' ? none : hostText}</span>
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div
          data-testid="incident-column"
          className="lg:col-span-2 min-w-0 flex flex-col gap-5"
        >
          <Panel
            title={message(locale, 'incident.investigation.title')}
            state={stateOf(detail, steps.length === 0)}
            dependency={dependencyOf(detail)}
            labels={panelLabels(
              locale,
              message(locale, 'incident.investigation.title'),
            )}
            action={
              hasInvestigation ? (
                <span
                  data-testid="investigation-summary"
                  className="flex items-center gap-2 text-meta text-muted"
                >
                  <span data-testid="summary-steps">
                    {stepCount === null
                      ? none
                      : message(
                          locale,
                          stepCount === 1
                            ? 'incident.investigation.steps.one'
                            : 'incident.investigation.steps.other',
                          { count: stepCount },
                        )}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span data-testid="summary-duration">
                    {durationMs === null
                      ? none
                      : formatDuration(locale, durationMs / 1000)}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span data-testid="summary-cost">
                    {cost === null ? none : formatCurrency(locale, cost, CURRENCY)}
                  </span>
                </span>
              ) : undefined
            }
            empty={{
              heading: message(locale, 'incident.investigation.empty.heading'),
              body: message(locale, 'incident.investigation.empty.body'),
              actionLabel: message(locale, 'incident.investigation.empty.action'),
              href: '/first-run',
            }}
          >
            <ol className="flex flex-col gap-4">
              {steps.map(({ entry, kind }, index) => {
                const at = timestamp(locale, text(entry, 'at'), now, zone);
                const cause = text(entry, 'cause');
                const detailText = text(entry, 'detail');
                return (
                  <li
                    key={`${kind}-${String(index)}`}
                    data-testid="investigation-step"
                    data-kind={kind}
                    className="flex gap-3"
                  >
                    <time
                      data-testid="step-time"
                      dateTime={at.iso}
                      title={at.relative}
                      className="text-meta text-muted tabular-nums shrink-0"
                    >
                      {at.absolute}
                    </time>
                    <div className="min-w-0 flex flex-col gap-1">
                      <p className="text-small">
                        <span className="text-strong">
                          {message(
                            locale,
                            STEP_HEADING[kind] ??
                              'incident.investigation.step.evidence',
                          )}
                        </span>
                        {' — '}
                        {/* On the receipt this sentence is what authenticated
                            the delivery — the recorder writes the credential's
                            display name into it, so naming it here is naming
                            the token rather than repeating it on a line of its
                            own. */}
                        <span
                          data-testid={
                            kind === 'receipt' ? 'delivery-token-name' : 'step-detail'
                          }
                        >
                          {cause === '' ? none : cause}
                        </span>
                      </p>
                      {kind === 'receipt' ? (
                        <span data-testid="step-labels" className="font-mono text-meta">
                          {detailText === '' ? none : detailText}
                        </span>
                      ) : null}
                      {kind === 'hypotheses' ? (
                        <ul className="flex flex-col gap-1">
                          {splitNonEmpty(detailText, '; ').map((hypothesis) => (
                            <li
                              key={hypothesis}
                              data-testid="hypothesis"
                              className="text-small"
                            >
                              {hypothesis}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      {kind === 'evidence' ? (
                        <div className="font-mono text-meta bg-sunken rounded-2 p-2 flex flex-col gap-1">
                          <p data-testid="evidence-query">
                            {text(entry, 'query') || none}
                          </p>
                          <p data-testid="evidence-result">
                            {text(entry, 'result') || none}
                          </p>
                        </div>
                      ) : null}
                      {kind === 'delivery' ? (
                        <p className="text-meta text-muted">
                          {splitNonEmpty(detailText, ', ').map(
                            (destination, position, all) => (
                              <span
                                key={destination}
                                data-testid="delivery-destination"
                              >
                                {destination}
                                {position < all.length - 1 ? ', ' : ''}
                              </span>
                            ),
                          )}
                        </p>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ol>
          </Panel>
        </div>

        <div data-testid="incident-column" className="flex flex-col gap-5 min-w-0">
          <Panel
            title={message(locale, 'incident.proposedAction.title')}
            state={stateOf(approvals, !hasProposal)}
            dependency={dependencyOf(approvals)}
            labels={panelLabels(
              locale,
              message(locale, 'incident.proposedAction.title'),
            )}
            empty={{
              heading: message(locale, 'incident.proposedAction.empty.heading'),
              body: message(locale, 'incident.proposedAction.empty.body'),
              actionLabel: message(locale, 'incident.proposedAction.empty.action'),
              href: hasInvestigation ? `/runs/${runId}` : '/first-run',
            }}
          >
            {/* This panel's own `state` is gated on `!hasProposal` above, so by
                the time children render here `proposal` is always defined and
                its diagnosis is always real. */}
            <div data-testid="proposed-action" className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <span data-testid="decision-state" className="text-strong">
                  {decisionLabel}
                </span>
              </div>
              <p data-testid="action-sentence" className="text-small">
                {actionSentence === '' ? none : actionSentence}
              </p>
              <p data-testid="blast-radius" className="text-meta text-muted">
                <span data-testid="radius-resources">
                  {radiusResourceCount === null
                    ? none
                    : message(
                        locale,
                        radiusResourceCount === 1
                          ? 'incident.proposedAction.radius.resources.one'
                          : 'incident.proposedAction.radius.resources.other',
                        { count: radiusResourceCount },
                      )}
                </span>
                {', '}
                <span data-testid="radius-zone">
                  {message(locale, 'incident.proposedAction.radius.zone', {
                    zone: zoneText,
                  })}
                </span>
                {', '}
                <span data-testid="radius-criticality">
                  {message(locale, 'incident.proposedAction.radius.criticality', {
                    criticality: radiusCriticalityText,
                  })}
                </span>
              </p>
              <p data-testid="posture" className="text-meta text-muted">
                {message(locale, 'incident.proposedAction.posture', {
                  posture: message(locale, 'shell.guardian.posture.propose'),
                })}
              </p>
              {decisionState === 'pending' ? (
                <IncidentDecisionControls
                  approvalId={proposalId}
                  labels={{
                    approve: message(locale, 'incident.proposedAction.approve'),
                    reject: message(locale, 'incident.proposedAction.reject'),
                    reason: message(locale, 'incident.proposedAction.reason'),
                    reasonRequired: message(
                      locale,
                      'incident.proposedAction.reasonRequired',
                    ),
                    failed: message(locale, 'incident.proposedAction.decisionFailed'),
                  }}
                />
              ) : null}
            </div>
          </Panel>

          <Panel
            title={message(locale, 'incident.evidenceTrail.title')}
            state={stateOf(detail, runId === '')}
            dependency={dependencyOf(detail)}
            labels={panelLabels(
              locale,
              message(locale, 'incident.evidenceTrail.title'),
            )}
            empty={{
              heading: message(locale, 'incident.evidenceTrail.empty.heading'),
              body: message(locale, 'incident.evidenceTrail.empty.body'),
              actionLabel: message(locale, 'incident.evidenceTrail.empty.action'),
              href: '/first-run',
            }}
          >
            {/* This panel's own `state` is gated on `runId === ''` above, so by
                the time children render here a run is always attached — the
                link never has nothing to point at. */}
            <div data-testid="evidence-trail" className="flex flex-col gap-2">
              <p className="text-meta text-muted">
                {message(locale, 'incident.evidenceTrail.body')}
              </p>
              <a
                href={`/runs/${runId}`}
                className="text-small underline underline-offset-2"
              >
                {message(locale, 'incident.evidenceTrail.link')}
              </a>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
