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
import { ProposalCard, type ProposalRow } from '../proposal';
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
  pairs,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';

/**
 * The "Actions" tab of Decisions: everything waiting on an approval, grouped by
 * how long it has waited, decidable where it is read.
 *
 * The grouping is by urgency rather than by run or by kind: an approval that has
 * passed its expiry is a different thing from one that arrived a minute ago, and
 * a queue sorted by identifier makes those two look the same.
 *
 * The decision controls are **absent** for a viewer who may not decide. Not
 * disabled: a disabled control still says the capability exists, still says
 * somebody else has it, and still ships the handler behind it.
 *
 * **This tab is one half of Decisions.** "Can the agent do this now" and
 * "should the deployment be different from tomorrow on" are different
 * questions, and used to be two menu entries with no reference to each other.
 * They are two tabs of one screen now — `screens/decisions.tsx`, which renders
 * this content and `proposals.tsx`'s side by side — so a reader who opens
 * either sees that the other exists without a cross-link paragraph doing the
 * work a tab bar already does.
 *
 * **The empty state names the rule, not only the mechanism.** "None does" is
 * true and unhelpful on a deployment where the approval threshold was never
 * touched; the useful sentence says which side-effect level is gated and
 * whether that is this deployment's own choice or the shipped default —
 * unless the setup itself is unfinished, in which case *that* is the more
 * useful thing to say, and it wins.
 */

/** The permission the gateway requires to decide a remediation. */
const DECIDE = 'remediation.approve';

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
 * Whether `record`'s window for being answered has closed, on the clock.
 *
 * Asked of the clock rather than of `state`, for the reason the deployment's
 * own refusal is: a lapsed change is relabelled by a sweep, and a deployment
 * whose sweep is not scheduled leaves every lapsed change sitting at
 * `pending`. Reading the label here would draw a live Approve over a change
 * the deployment will refuse — which is the same reading that let a
 * remediation with a fifteen-minute window be approved fifty minutes late.
 *
 * One function rather than two readings of the same field, because the two
 * things this decides are the two that used to disagree: which group the card
 * is filed under, and whether it is offered a control.
 */
function hasExpired(record: unknown, now: Date): boolean {
  const expires = Date.parse(text(record, 'expires_at'));
  return !Number.isNaN(expires) && expires < now.getTime();
}

/** Which group an approval belongs to, by how long it has been waiting. */
function groupOf(record: unknown, now: Date): 'overdue' | 'today' | 'later' {
  if (hasExpired(record, now)) return 'overdue';
  const requested = Date.parse(text(record, 'requested_at'));
  const day = 24 * 60 * 60 * 1000;
  if (!Number.isNaN(requested) && now.getTime() - requested < day) return 'today';
  return 'later';
}

export async function ApprovalsTab(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone, search } = context;
  const init = authorised(credential);

  const approvals = await panelRead('/v1/approvals', () => read('/v1/approvals', init));
  const pending = list(dataOf(approvals), 'approvals').filter(
    (record) => text(record, 'state') === 'pending',
  );

  // One read per run, for the interaction each approval is answered through.
  // The API addresses a decision by interaction rather than by approval, and a
  // console that guessed the identifier would be a console that decided the
  // wrong thing exactly once.
  const runs = [...new Set(pending.map((record) => text(record, 'run_id')))];
  const interactions = new Map<string, string>();
  await Promise.all(
    runs.map(async (runId) => {
      const answered = await panelRead('/v1/investigations/{run_id}/interactions', () =>
        read('/v1/investigations/{run_id}/interactions', {
          ...init,
          params: { run_id: runId },
        }),
      );
      const open = list(dataOf(answered), 'interactions').find((record) =>
        flag(record, 'is_open'),
      );
      if (open !== undefined) {
        interactions.set(runId, text(open, 'interaction_id'));
      }
    }),
  );

  const none = message(locale, 'surface.none');
  const decidable = may(viewer, DECIDE);

  // --- Why the queue reads as it does, when there is nothing in it -----------
  //
  // An unfinished setup is the more useful thing to say and wins outright: a
  // deployment that cannot investigate yet has no approvals for a reason no
  // policy sentence explains. Once the setup is done, the mechanism ("a change
  // that needs a person appears here") is true and says nothing about *this*
  // deployment, so the rule that actually feeds the queue is read and named —
  // the side-effect level it is gated above, and whether that is this
  // deployment's own choice or the level nobody has moved off yet.
  const setup = await readSetupState(credential);
  const cause = setupCause(locale, setup, INVESTIGATION_STEP);

  let emptyBody = message(locale, 'approvals.empty.body');
  if (cause === null && pending.length === 0) {
    const tree = await optionalRead('/v1/config', () => read('/v1/config', init));
    const nodeId = resolveNode(
      readViewState(search, ['node']),
      viewer,
      placedTree(dataOf(tree)),
    );
    if (nodeId !== '') {
      const fields = await optionalRead('/v1/config/{node_id}/fields', () =>
        read('/v1/config/{node_id}/fields', { ...init, params: { node_id: nodeId } }),
      );
      let rule = ruleFromFields(dataOf(fields));
      if (rule === null) {
        // The mockplane still serves the pre-schema effective-config shape. Keep
        // this compatibility read local while recorded scenarios migrate; the
        // live path above remains the source of the default and its provenance.
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

  /**
   * The controls this proposal is decided with, or nothing for a viewer who
   * may not decide.
   *
   * Two routes, because there are two things called a proposal here. One is a
   * question a live investigation is blocked on — an *interaction* — answered
   * through the run that raised it. The other is a remediation the gate queued
   * as an approval in the store, which raises no interaction and is answered
   * at the approval itself.
   *
   * Only the first was ever wired. So a queued remediation matched no
   * interaction, the controls were dropped, and a screen called Decisions
   * showed a card saying "awaiting your decision" with nothing on it to decide
   * with. The interaction is still preferred when there is one: answering
   * through the run releases an investigation that is standing still waiting
   * for it, and deciding at the store would leave it standing there.
   *
   * **A closed window is answered before either of them, and before the
   * viewer's permission.** The deployment refuses a decision taken after the
   * expiry, so an Approve on a lapsed card is a button whose only outcome is
   * an error — and this screen already knows, because it filed the card under
   * "Past its expiry" to say so. What goes in the control's place is the
   * reason, not a gap: a card that merely lost its buttons reads as a
   * permission the viewer does not hold, and sends them to ask for one that
   * would not have helped. Which is also why the expiry is checked above
   * `decidable` rather than inside it — a closed window is closed for
   * everyone, exactly as the deployment's own check has it.
   */
  function decisionFor(
    record: unknown,
    interactionId: string | undefined,
  ): { decision?: ReactNode } {
    if (hasExpired(record, now)) {
      return {
        decision: (
          <p data-testid="window-closed" className="text-small text-muted">
            {message(locale, 'approvals.expired.note')}
          </p>
        ),
      };
    }
    if (!decidable) return {};
    const labels = {
      approve: message(locale, 'proposal.approve'),
      reject: message(locale, 'proposal.reject'),
      reason: message(locale, 'proposal.reason'),
      reasonRequired: message(locale, 'proposal.reason.required'),
    };
    if (interactionId !== undefined) {
      return {
        decision: <DecisionControls interactionId={interactionId} labels={labels} />,
      };
    }
    const approvalId = text(record, 'approval_id');
    if (approvalId === '') return {};
    return {
      decision: (
        <IncidentDecisionControls
          approvalId={approvalId}
          labels={{
            ...labels,
            failed: message(locale, 'incident.proposedAction.decisionFailed'),
          }}
        />
      ),
    };
  }

  function rowsFor(record: unknown): readonly ProposalRow[] {
    const plan = field(record, 'rollback_plan');
    const steps = list(plan, 'steps');
    const arguments_ = pairs(record, 'arguments')
      .map(([name, value]) => `${name} = ${value}`)
      .join(' · ');

    return [
      {
        field: 'target',
        label: message(locale, 'proposal.target'),
        value: arguments_ === '' ? none : arguments_,
      },
      {
        field: 'current',
        label: message(locale, 'proposal.current'),
        value: text(record, 'state'),
      },
      {
        field: 'change',
        label: message(locale, 'proposal.change'),
        value: `${text(record, 'action')} — ${text(record, 'summary')}`,
      },
      {
        field: 'protects',
        label: message(locale, 'proposal.protects'),
        value: steps.length === 0 ? none : '',
        items: steps.map((step) => ({
          badge: text(step, 'capability'),
          text: text(step, 'description'),
        })),
      },
      {
        field: 'blast',
        label: message(locale, 'proposal.blast'),
        value: text(plan, 'notes') === '' ? none : text(plan, 'notes'),
      },
      {
        field: 'rollback',
        label: message(locale, 'proposal.rollback'),
        value:
          steps.length === 0
            ? message(locale, 'proposal.norollback')
            : text(plan, 'plan_id'),
        grave: steps.length === 0,
      },
      {
        field: 'verification',
        label: message(locale, 'proposal.verification'),
        value: none,
      },
      {
        field: 'autonomy',
        label: message(locale, 'proposal.autonomy'),
        value: `${sideEffectLabel(locale, text(record, 'side_effect_level'))} ${message(locale, 'proposal.queued')}`,
      },
    ];
  }

  const groups = (['overdue', 'today', 'later'] as const).map((group) => ({
    group,
    label: message(locale, `approvals.group.${group}`),
    records: pending.filter((record) => groupOf(record, now) === group),
  }));

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
        state={stateOf(approvals, pending.length === 0)}
        dependency={dependencyOf(approvals)}
        labels={panelLabels(locale, message(locale, 'approvals.title'))}
        empty={empty}
        bare
      >
        <div className="flex flex-col gap-5">
          {groups
            .filter((group) => group.records.length > 0)
            .map((group) => (
              <section
                key={group.group}
                data-testid="approval-group"
                data-group={group.group}
              >
                <h4 className="text-strong mb-2">{group.label}</h4>
                <div className="flex flex-col gap-4">
                  {group.records.map((record) => {
                    const id = text(record, 'approval_id');
                    const interactionId = interactions.get(text(record, 'run_id'));
                    const waited = timestamp(
                      locale,
                      text(record, 'requested_at'),
                      now,
                      zone,
                    );
                    return (
                      <div key={id} data-testid="approval" data-approval={id}>
                        <ProposalCard
                          heading={message(locale, 'proposal.title')}
                          risk={message(locale, 'proposal.risk', {
                            level: String(
                              Math.max(
                                1,
                                Math.min(5, number(record, 'risk_class') || 3),
                              ),
                            ),
                          })}
                          rows={rowsFor(record)}
                          {...decisionFor(record, interactionId)}
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
              </section>
            ))}
        </div>
      </Panel>
    </>
  );
}
