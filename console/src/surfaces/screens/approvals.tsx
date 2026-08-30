import type { ReactNode } from 'react';

import { message } from '@/i18n/messages';
import { timestamp } from '@/i18n/format';
import { may } from '@/session/viewer';
import type { SurfaceContext } from '../context';
import { DecisionControls } from '../decision';
import { IncidentDecisionControls } from './incident-decision-controls';
import { emptyBecause, readSetupState, setupCause } from '../emptiness';
import { INVESTIGATION_STEP } from '../first-run/plan';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { DecisionCard, type ActionStep, type DecisionCardProps, type EvidenceItem } from '../proposal';
import { sideEffectLabel } from '../side-effects';
import { placedTree } from '../tree';
import { readViewState, resolveNode } from '../url-state';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  number,
  optionalRead,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';

/**
 * The "Actions" tab of Decisions: the agent's action, by field, and the
 * expired one with an exit — `design/padrao-2026-08/Decisions.dc.html`.
 *
 * Three reads rather than one: `state=pending`, `state=expired`,
 * `state=decided`, because FR-006 makes the three buckets the gateway's own
 * concern and a screen that filtered one list into three would be a second
 * opinion about what "expired" means. Every one of them sweeps lapsed
 * requests server-side before answering (`GET /v1/approvals`, T015), so
 * "expired" here is never a client-side clock comparison.
 *
 * **The decision controls are absent for a viewer who may not decide.** Not
 * disabled — a disabled control still says the capability exists and still
 * ships the handler behind it.
 *
 * **Two live decide-in-place paths, both composed unedited.** An approval
 * whose run has an open interaction gets `DecisionControls`
 * (`/v1/interactions/{id}/approve|reject`); one without gets
 * `IncidentDecisionControls` (`/v1/approvals/{id}/decision`) — the only path
 * staging exercises today, since it has no live run. Neither component's
 * interface changes here.
 */

/** The permission the gateway requires to decide a remediation.
 *
 * `approval.review` (`Permission.APPROVAL_REVIEW`) — the same right
 * `POST /v1/approvals/{id}/decision` itself checks
 * (`gateway/http/security/console_routes.py`). The screen used to gate on
 * `remediation.approve`, a real permission that happens to exist but is not
 * the one this route enforces; every role that has one has had the other too
 * so far, which is exactly the kind of drift that only shows up the day a
 * custom role does not.
 */
const DECIDE = 'approval.review';

/**
 * The configuration paths used by the live API and the recorded mockplane.
 *
 * The live configuration schema nests this under ``policies.approvals``. Older
 * recorded scenarios expose the pre-schema flat name, so the fallback is kept at
 * this boundary rather than making the rest of the screen know about two APIs.
 */
const APPROVAL_POLICY_PATHS = [
  'policies.approvals.threshold',
  'approval.required_above',
] as const;

interface ApprovalRule {
  readonly threshold: string;
  readonly provenance: string;
}

/** Read a string at a dotted path, accepting the legacy flat key as well. */
function dottedText(record: unknown, path: string): string {
  const direct = text(record, path);
  if (direct !== '') return direct;

  let current: unknown = record;
  for (const segment of path.split('.')) {
    current = field(current, segment);
  }
  return typeof current === 'string' ? current : '';
}

/** Return the policy field that describes the active approval threshold. */
function ruleFromFields(payload: unknown): ApprovalRule | null {
  const declared = list(payload, 'fields').find((record) =>
    APPROVAL_POLICY_PATHS.some((path) => text(record, 'path') === path),
  );
  if (declared === undefined) return null;

  const threshold = text(declared, 'value') || text(declared, 'default');
  return threshold === ''
    ? null
    : { threshold, provenance: text(declared, 'provenance') };
}

/** Return the policy from an effective-config response when using an old fixture. */
function ruleFromEffective(payload: unknown): ApprovalRule | null {
  const values = field(payload, 'values');
  const provenance = field(payload, 'provenance');
  for (const path of APPROVAL_POLICY_PATHS) {
    const threshold = dottedText(values, path);
    if (threshold !== '') {
      return { threshold, provenance: dottedText(provenance, path) };
    }
  }
  return null;
}

/**
 * The route an evidence reference resolves to.
 *
 * References are `source:kind:id` (spec, fact 2 —
 * `alertmanager:incident_timeline:res-7a73…`, `proxmox:quorum:HAL9000`). Never
 * empty (AN-11): an unparsable reference still lands somewhere rather than on
 * a link with no destination.
 */
function hrefForEvidence(reference: string): string {
  const parts = reference.split(':');
  const id = parts[parts.length - 1] ?? '';
  if (id === '') return '#';
  const kind = parts.length > 1 ? (parts[1] ?? '') : '';
  if (kind.includes('incident')) return `/incidents/${encodeURIComponent(id)}`;
  return `/resources/${encodeURIComponent(id)}`;
}

function stepsOf(record: unknown, key: string): readonly ActionStep[] {
  return list(record, key).map((entry) => ({
    ordinal: number(entry, 'ordinal'),
    summary: text(entry, 'summary'),
    capability: text(entry, 'capability'),
  }));
}

function evidenceOf(record: unknown): readonly EvidenceItem[] {
  return list(record, 'evidence').map((entry) => {
    const reference = text(entry, 'reference');
    return {
      summary: text(entry, 'summary'),
      href: hrefForEvidence(reference),
    };
  });
}

/** "N resource(s) known, depth D" — or that the graph could not be read. */
function blastRadiusTextOf(locale: Parameters<typeof message>[0], record: unknown): string {
  const radius = field(record, 'blast_radius');
  if (!flag(radius, 'known')) {
    return message(locale, 'decisions.card.blastRadius.unknown');
  }
  return message(locale, 'decisions.card.blastRadius.text', {
    count: String(number(radius, 'count')),
    depth: String(number(radius, 'depth')),
  });
}

function autonomyTextOf(locale: Parameters<typeof message>[0], record: unknown): string {
  const autonomy = field(record, 'autonomy');
  const level = text(autonomy, 'side_effect_level');
  const reversible = flag(autonomy, 'reversible');
  return reversible
    ? message(locale, 'decisions.card.autonomy.reversible', { level: sideEffectLabel(locale, level) })
    : message(locale, 'decisions.card.autonomy.irreversible', { level: sideEffectLabel(locale, level) });
}

/**
 * The controls this decision is decided with, or nothing for a viewer who
 * may not decide.
 *
 * Two routes, because there are two things called a decision here. One is a
 * question a live investigation is blocked on — an *interaction* — answered
 * through the run that raised it. The other is a remediation the gate queued
 * as an approval in the store, which raises no interaction and is answered
 * at the approval itself. The interaction is preferred when there is one:
 * answering through the run releases an investigation standing still waiting
 * for it.
 */
function decisionFor(
  locale: Parameters<typeof message>[0],
  decidable: boolean,
  record: unknown,
  interactionId: string | undefined,
): ReactNode {
  if (!decidable) return undefined;
  const labels = {
    approve: message(locale, 'proposal.approve'),
    reject: message(locale, 'proposal.reject'),
    reason: message(locale, 'proposal.reason'),
    reasonRequired: message(locale, 'proposal.reason.required'),
  };
  if (interactionId !== undefined) {
    return <DecisionControls interactionId={interactionId} labels={labels} />;
  }
  const approvalId = text(record, 'approval_id');
  if (approvalId === '') return undefined;
  return (
    <IncidentDecisionControls
      approvalId={approvalId}
      labels={{ ...labels, failed: message(locale, 'incident.proposedAction.decisionFailed') }}
    />
  );
}

function cardPropsFrom(
  locale: Parameters<typeof message>[0],
  record: unknown,
  state: DecisionCardProps['state'],
): Omit<DecisionCardProps, 'decision' | 'expiredFooter' | 'outcome'> {
  const risk = field(record, 'risk');
  const origin = field(record, 'origin');
  const originIncidentId = text(origin, 'incident_id');
  const originHeadline = text(origin, 'headline');
  return {
    approvalId: text(record, 'approval_id'),
    state,
    title: text(record, 'title') || text(record, 'summary'),
    requester: text(record, 'requester'),
    ...(originIncidentId === ''
      ? {}
      : { originHref: `/incidents/${encodeURIComponent(originIncidentId)}` }),
    ...(originHeadline === '' ? {} : { originLabel: originHeadline }),
    category: text(record, 'category') || 'remediation',
    risk: {
      class: text(risk, 'class'),
      score: number(risk, 'score') || 1,
      scale: number(risk, 'scale') || 5,
    },
    steps: stepsOf(record, 'steps'),
    rollback: stepsOf(record, 'rollback'),
    reversible: flag(field(record, 'autonomy'), 'reversible'),
    why: text(record, 'intent'),
    evidence: evidenceOf(record),
    blastRadiusText: blastRadiusTextOf(locale, record),
    autonomyText: autonomyTextOf(locale, record),
    rawPayload: JSON.stringify(field(record, 'raw'), null, 2),
    labels: cardLabels(locale),
    summaryFallback: text(record, 'summary'),
  };
}

/** The card's own section labels, resolved once per render rather than per card. */
function cardLabels(locale: Parameters<typeof message>[0]): DecisionCardProps['labels'] {
  return {
    steps: message(locale, 'decisions.card.steps'),
    rollback: message(locale, 'decisions.card.rollback'),
    noRollback: message(locale, 'decisions.card.noRollback'),
    why: message(locale, 'decisions.card.why'),
    evidence: message(locale, 'decisions.card.evidence'),
    evidenceLink: message(locale, 'decisions.card.evidenceLink'),
    blastRadius: message(locale, 'decisions.card.blastRadius'),
    rawPayload: message(locale, 'decisions.card.rawPayload'),
    notRecorded: message(locale, 'decisions.card.notRecorded'),
    risk: message(locale, 'decisions.card.risk'),
    outcome: message(locale, 'decisions.card.outcome'),
    appliedAndVerified: message(locale, 'decisions.card.appliedAndVerified'),
  };
}

export async function ApprovalsTab(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone, search } = context;
  const init = authorised(credential);

  const pendingRead = await panelRead('/v1/approvals?state=pending', () =>
    read('/v1/approvals', { ...init, query: '?state=pending' }),
  );
  const expiredRead = await panelRead('/v1/approvals?state=expired', () =>
    read('/v1/approvals', { ...init, query: '?state=expired' }),
  );
  const decidedRead = await panelRead('/v1/approvals?state=decided', () =>
    read('/v1/approvals', { ...init, query: '?state=decided&limit=10' }),
  );

  const pending = list(dataOf(pendingRead), 'approvals');
  const expired = list(dataOf(expiredRead), 'approvals');
  const decided = list(dataOf(decidedRead), 'approvals');
  const queue = [...expired, ...pending];

  // One read per run with a queued or expired decision, for the interaction
  // it might be answered through. The API addresses a decision by
  // interaction rather than by approval, and a console that guessed the
  // identifier would be a console that decided the wrong thing exactly once.
  const runs = [...new Set(queue.map((record) => text(record, 'run_id')).filter((id) => id !== ''))];
  const interactions = new Map<string, string>();
  await Promise.all(
    runs.map(async (runId) => {
      const answered = await panelRead('/v1/investigations/{run_id}/interactions', () =>
        read('/v1/investigations/{run_id}/interactions', {
          ...init,
          params: { run_id: runId },
        }),
      );
      const open = list(dataOf(answered), 'interactions').find((record) => flag(record, 'is_open'));
      if (open !== undefined) {
        interactions.set(runId, text(open, 'interaction_id'));
      }
    }),
  );

  const none = message(locale, 'surface.none');
  const decidable = may(viewer, DECIDE);
  const failed = pendingRead.status === 'error' || expiredRead.status === 'error';

  // --- Why the queue reads as it does, when there is nothing in it -----------
  const setup = await readSetupState(credential);
  const cause = setupCause(locale, setup, INVESTIGATION_STEP);

  let emptyBody = message(locale, 'approvals.empty.body');
  if (cause === null && queue.length === 0) {
    const tree = await optionalRead('/v1/config', () => read('/v1/config', init));
    const nodeId = resolveNode(readViewState(search, ['node']), viewer, placedTree(dataOf(tree)));
    if (nodeId !== '') {
      const fields = await optionalRead('/v1/config/{node_id}/fields', () =>
        read('/v1/config/{node_id}/fields', { ...init, params: { node_id: nodeId } }),
      );
      let rule = ruleFromFields(dataOf(fields));
      if (rule === null) {
        const effective = await optionalRead('/v1/config/{node_id}', () =>
          read('/v1/config/{node_id}', { ...init, params: { node_id: nodeId } }),
        );
        rule = ruleFromEffective(dataOf(effective));
      }
      if (rule !== null) {
        emptyBody = [
          emptyBody,
          message(locale, 'approvals.empty.rule', { threshold: rule.threshold }),
          rule.provenance === ''
            ? message(locale, 'approvals.empty.rule.default')
            : message(locale, 'approvals.empty.rule.setAt', { node: rule.provenance }),
        ].join(' ');
      }
    }
  }

  const empty = emptyBecause(
    {
      heading: message(locale, 'approvals.empty.heading'),
      body: emptyBody,
      actionLabel: message(locale, 'approvals.empty.action'),
      href: '/runs',
    },
    cause,
  );

  return (
    <>
      <Panel
        title={message(locale, 'approvals.title')}
        state={failed ? 'error' : stateOf(pendingRead, queue.length === 0)}
        dependency={failed ? dependencyOf(expiredRead.status === 'error' ? expiredRead : pendingRead) : ''}
        labels={panelLabels(locale, message(locale, 'approvals.title'))}
        empty={empty}
        bare
      >
        <div className="flex flex-col gap-5">
          {queue.map((record, index) => {
            const id = text(record, 'approval_id');
            const state = text(record, 'state') as DecisionCardProps['state'];
            const isExpired = state === 'expired';
            const interactionId = interactions.get(text(record, 'run_id'));
            const waited = timestamp(locale, text(record, 'requested_at'), now, zone);

            if (index > 0) {
              // Only the first card in the combined, oldest-and-most-urgent
              // ordering is expanded — the rest render as one-sentence rows,
              // per the "many pending" edge case.
              return (
                <div
                  key={id}
                  data-testid="decision-row-collapsed"
                  data-approval={id}
                  className="flex items-center gap-3 px-4 py-2 rounded-2 edge border-border bg-raised"
                >
                  <span className="text-small min-w-0 truncate">{text(record, 'title')}</span>
                  <span className="ml-auto text-meta text-muted shrink-0">
                    {message(locale, 'proposal.risk', { level: String(number(field(record, 'risk'), 'score') || 1) })}
                  </span>
                  <time
                    className="text-meta text-muted shrink-0"
                    dateTime={waited.iso}
                    title={waited.absolute}
                  >
                    {waited.relative}
                  </time>
                </div>
              );
            }

            const cardProps = cardPropsFrom(locale, record, isExpired ? 'expired' : 'pending');
            return (
              <div key={id}>
                <DecisionCard
                  {...cardProps}
                  {...(isExpired
                    ? {
                        expiredFooter: {
                          approvalId: id,
                          labels: {
                            explanation: message(locale, 'decisions.expiredFooter.explanation'),
                            repropose: message(locale, 'decisions.expiredFooter.repropose'),
                            discard: message(locale, 'decisions.expiredFooter.discard'),
                            failed: message(locale, 'decisions.expiredFooter.failed'),
                          },
                        },
                      }
                    : { decision: decisionFor(locale, decidable, record, interactionId) })}
                />
                <p className="text-meta text-muted mt-1">
                  <time dateTime={waited.iso} title={waited.absolute}>
                    {waited.relative}
                  </time>
                </p>
              </div>
            );
          })}
        </div>
      </Panel>

      <section
        data-testid="decided-list"
        className="rounded-3 edge border-border bg-raised p-4 flex flex-col gap-2 mt-4"
      >
        <h4 className="text-strong">{message(locale, 'decisions.decided.heading')}</h4>
        {decided.length === 0 ? (
          <p data-testid="decided-empty" className="text-small text-muted">
            {message(locale, 'decisions.decided.empty')}
          </p>
        ) : (
          decided.map((record) => {
            const verdict = text(record, 'verdict');
            const decidedAt = timestamp(locale, text(record, 'decided_at'), now, zone);
            const who = text(record, 'decided_by') || none;
            const reason = text(record, 'reason');
            const outcome =
              verdict === 'approved'
                ? flag(record, 'applied_and_verified')
                  ? message(locale, 'decisions.decided.outcome.approvedVerified', { who })
                  : message(locale, 'decisions.decided.outcome.approved', { who })
                : verdict === 'rejected'
                  ? reason === ''
                    ? message(locale, 'decisions.decided.outcome.rejectedNoReason', { who })
                    : message(locale, 'decisions.decided.outcome.rejected', { who, reason })
                  : message(locale, 'decisions.decided.outcome.discarded', { who });
            return (
              <div
                key={text(record, 'approval_id')}
                data-testid="decided-item"
                data-verdict={verdict}
                className="flex items-center gap-2 py-2 edge border-border border-t-0 border-x-0 last:border-b-0"
              >
                <span className="text-small min-w-0 truncate">
                  {text(record, 'title')} — {outcome}
                </span>
                <time
                  className="ml-auto text-meta text-muted shrink-0"
                  dateTime={decidedAt.iso}
                  title={decidedAt.absolute}
                >
                  {decidedAt.relative}
                </time>
              </div>
            );
          })
        )}
      </section>
    </>
  );
}
