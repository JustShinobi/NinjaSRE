import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { CompassIcon } from '@/design/icons';
import { message } from '@/i18n/messages';
import { timestamp } from '@/i18n/format';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { DecisionControls } from '../decision';
import { emptyBecause, readSetupState, setupCause } from '../emptiness';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { ProposalCard, type ProposalRow } from '../proposal';
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
 * Everything waiting on a decision, grouped by how long it has waited, decidable
 * where it is read.
 *
 * The grouping is by urgency rather than by run or by kind: an approval that has
 * passed its expiry is a different thing from one that arrived a minute ago, and
 * a queue sorted by identifier makes those two look the same.
 *
 * The decision controls are **absent** for a viewer who may not decide. Not
 * disabled: a disabled control still says the capability exists, still says
 * somebody else has it, and still ships the handler behind it.
 *
 * **This is not the only inbox.** "Approvals" and "Proposed changes" are both
 * queues of a human decision, and the difference — can the agent do this now,
 * versus should the deployment be different from tomorrow on — is real but is
 * not carried by either name. This screen says so, with a line to the other
 * queue, because the structural fix (one inbox, two tabs) is a later change and
 * this one is not.
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
 * The configuration path the queue is gated on.
 *
 * The API's own dotted spelling, a flat key rather than a nested one — the
 * same path `locked` and `approval_gated` name on a configuration write, so a
 * reader comparing the two screens is comparing the same field.
 */
const THRESHOLD_PATH = 'approval.required_above';

/** Which group an approval belongs to, by how long it has been waiting. */
function groupOf(record: unknown, now: Date): 'overdue' | 'today' | 'later' {
  const expires = Date.parse(text(record, 'expires_at'));
  if (!Number.isNaN(expires) && expires < now.getTime()) return 'overdue';
  const requested = Date.parse(text(record, 'requested_at'));
  const day = 24 * 60 * 60 * 1000;
  if (!Number.isNaN(requested) && now.getTime() - requested < day) return 'today';
  return 'later';
}

export async function ApprovalsScreen(context: SurfaceContext): Promise<ReactNode> {
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
  const cause = setupCause(locale, setup);

  let emptyBody = message(locale, 'approvals.empty.body');
  if (cause === null && pending.length === 0) {
    const tree = await optionalRead('/v1/config', () => read('/v1/config', init));
    const nodeId = resolveNode(
      readViewState(search, ['node']),
      viewer,
      placedTree(dataOf(tree)),
    );
    if (nodeId !== '') {
      const effective = await optionalRead('/v1/config/{node_id}', () =>
        read('/v1/config/{node_id}', { ...init, params: { node_id: nodeId } }),
      );
      const payload = dataOf(effective);
      const threshold = text(field(payload, 'values'), THRESHOLD_PATH);
      const setAt = text(field(payload, 'provenance'), THRESHOLD_PATH);
      if (threshold !== '') {
        emptyBody = [
          emptyBody,
          `${message(locale, 'configuration.gated')}: ${threshold}.`,
          `${message(locale, 'configuration.column.provenance')} ${
            setAt === '' ? message(locale, 'configuration.editor.inherited') : setAt
          }.`,
        ].join(' ');
      }
    }
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
        value: `${text(record, 'side_effect_level')} — ${message(locale, 'proposal.queued')}`,
      },
    ];
  }

  const groups = (['overdue', 'today', 'later'] as const).map((group) => ({
    group,
    label: message(locale, `approvals.group.${group}`),
    records: pending.filter((record) => groupOf(record, now) === group),
  }));

  const proposals = areaFor('proposals');
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
      <AreaHeader area={areaFor('approvals')} locale={locale} />

      {/* Absent for a viewer who may not open the other queue at all — a link
          to a screen somebody cannot see is not a courtesy, it is a dead end
          dressed as one. */}
      {may(viewer, proposals.permission) ? (
        <p className="text-meta text-muted mb-3 flex items-center gap-1">
          <CompassIcon size="empty" />
          <Link href={proposals.path} data-testid="approvals-elsewhere">
            {message(locale, 'surface.open')} {message(locale, proposals.title)}
          </Link>
        </p>
      ) : null}

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
                          {...(decidable && interactionId !== undefined
                            ? {
                                decision: (
                                  <DecisionControls
                                    interactionId={interactionId}
                                    labels={{
                                      approve: message(locale, 'proposal.approve'),
                                      reject: message(locale, 'proposal.reject'),
                                      reason: message(locale, 'proposal.reason'),
                                      reasonRequired: message(
                                        locale,
                                        'proposal.reason.required',
                                      ),
                                    }}
                                  />
                                ),
                              }
                            : {})}
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
