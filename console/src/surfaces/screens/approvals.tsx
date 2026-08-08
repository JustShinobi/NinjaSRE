import type { ReactNode } from 'react';

import { message } from '@/i18n/messages';
import { timestamp } from '@/i18n/format';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { DecisionControls } from '../decision';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { ProposalCard, type ProposalRow } from '../proposal';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  number,
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
 */

/** The permission the gateway requires to decide a remediation. */
const DECIDE = 'remediation.approve';

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
  const { credential, locale, viewer, now, zone } = context;
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

  return (
    <>
      <AreaHeader area={areaFor('approvals')} locale={locale} />

      <Panel
        title={message(locale, 'approvals.title')}
        state={stateOf(approvals, pending.length === 0)}
        dependency={dependencyOf(approvals)}
        labels={panelLabels(locale, message(locale, 'approvals.title'))}
        empty={{
          heading: message(locale, 'approvals.empty.heading'),
          body: message(locale, 'approvals.empty.body'),
          actionLabel: message(locale, 'approvals.empty.action'),
          href: '/runs',
        }}
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
