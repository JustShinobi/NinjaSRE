import type { ReactNode } from 'react';

import { message } from '@/i18n/messages';
import { timestamp } from '@/i18n/format';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { ProposalReview } from '../proposal-review';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  list,
  number,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';

/**
 * Everything the agent has proposed and nobody has decided.
 *
 * One list rather than one per origin. A reviewer's question is "what is
 * waiting on me", not "what is waiting on me about detectors", and three lists
 * would be three places to look before the answer is none.
 *
 * Each row carries the four things a decision rests on, always in the same
 * order: what would change, why, the evidence, and the investigation it came
 * out of. The origin is a link rather than a sentence — a reviewer who cannot
 * reach the run cannot check the claim, and a proposal nobody can check is one
 * that gets approved because disagreeing with it would take twenty minutes.
 *
 * **The acceptance figure carries both numbers.** Sixty per cent of five and
 * sixty per cent of two hundred are different facts about a team, and a screen
 * showing only the percentage lets the first pass for the second.
 */

/** The permission the gateway requires to decide a proposal. */
const DECIDE = 'approval.review';

/** The kinds whose effect is their own words, needing no round trip to show. */
const TEXTUAL = new Set(['text']);

export async function ProposalsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone } = context;
  const init = authorised(credential);

  const queue = await panelRead('/v1/proposals', () => read('/v1/proposals', init));
  const body = dataOf(queue);
  const proposals = list(body, 'proposals');
  const acceptance = field(body, 'acceptance');
  const decidable = may(viewer, DECIDE);

  const decided = number(acceptance, 'decided');
  const figure =
    decided === 0
      ? message(locale, 'proposals.acceptance.none')
      : message(locale, 'proposals.acceptance', {
          approved: String(number(acceptance, 'approved')),
          decided: String(decided),
        });

  return (
    <>
      <AreaHeader area={areaFor('proposals')} locale={locale} />

      <Panel
        title={message(locale, 'proposals.title')}
        state={stateOf(queue, proposals.length === 0)}
        dependency={dependencyOf(queue)}
        labels={panelLabels(locale, message(locale, 'proposals.title'))}
        empty={{
          heading: message(locale, 'proposals.empty.heading'),
          body: message(locale, 'proposals.empty.body'),
          actionLabel: message(locale, 'proposals.empty.action'),
          href: '/runs',
        }}
        bare
      >
        <p className="text-meta text-muted mb-3" data-testid="acceptance">
          {figure}
        </p>
        <div className="flex flex-col gap-4">
          {proposals.map((record) => {
            const id = text(record, 'proposal_id');
            const kind = text(record, 'proposal_type');
            const effect = field(record, 'effect');
            const mechanism = text(effect, 'mechanism');
            const waited = timestamp(locale, text(record, 'proposed_at'), now, zone);
            const runId = text(record, 'run_id');
            const evidence = list(record, 'evidence').map((entry) => String(entry));
            const prior = list(record, 'prior_rejections');

            return (
              <section
                key={id}
                data-testid="proposal-item"
                data-proposal={id}
                data-kind={kind}
                className="rounded-3 edge border-border bg-raised p-4 flex flex-col gap-3"
              >
                <header className="flex items-baseline gap-2 flex-wrap">
                  <h3 className="text-section">{text(record, 'summary')}</h3>
                  <span className="text-micro uppercase edge border-border rounded-1 px-2 text-muted">
                    {message(locale, kindKey(kind))}
                  </span>
                  <time
                    className="ml-auto text-meta text-muted"
                    dateTime={waited.iso}
                    title={waited.absolute}
                  >
                    {waited.relative}
                  </time>
                </header>

                <dl className="grid grid-cols-1 gap-2 sm:grid-cols-4">
                  <dt className="text-meta text-muted">
                    {message(locale, 'proposals.field.rationale')}
                  </dt>
                  <dd className="text-small sm:col-span-3 min-w-0">
                    {text(record, 'rationale')}
                  </dd>
                  <dt className="text-meta text-muted">
                    {message(locale, 'proposals.field.evidence')}
                  </dt>
                  <dd className="text-small sm:col-span-3 min-w-0">
                    <ul className="flex flex-col gap-1">
                      {evidence.map((entry) => (
                        <li key={entry} className="break-all">
                          {entry}
                        </li>
                      ))}
                    </ul>
                  </dd>
                  <dt className="text-meta text-muted">
                    {message(locale, 'proposals.field.node')}
                  </dt>
                  <dd className="text-small sm:col-span-3 min-w-0 break-all">
                    {text(record, 'node_id')}
                  </dd>
                  <dt className="text-meta text-muted">
                    {message(locale, 'proposals.field.origin')}
                  </dt>
                  <dd className="text-small sm:col-span-3 min-w-0">
                    <a
                      className="underline break-all"
                      data-testid="origin-run"
                      href={`/runs/${runId}`}
                    >
                      {runId === '' ? message(locale, 'surface.none') : runId}
                    </a>
                  </dd>
                </dl>

                {prior.length === 0 ? null : (
                  <section
                    data-testid="prior-rejections"
                    className="flex flex-col gap-1"
                  >
                    <h4 className="text-meta text-danger">
                      {message(locale, 'proposals.prior.heading')}
                    </h4>
                    <ul className="flex flex-col gap-1">
                      {prior.map((entry) => {
                        const at = timestamp(
                          locale,
                          text(entry, 'decided_at'),
                          now,
                          zone,
                        );
                        return (
                          <li key={text(entry, 'proposal_id')} className="text-small">
                            {message(locale, 'proposals.prior.entry', {
                              who: text(entry, 'decided_by'),
                              when: at.relative,
                              reason: text(entry, 'reason'),
                            })}
                          </li>
                        );
                      })}
                    </ul>
                  </section>
                )}

                <ProposalReview
                  proposalId={id}
                  kind={kind}
                  mechanism={mechanism}
                  target={text(effect, 'target')}
                  payload={payloadOf(record)}
                  finalText={TEXTUAL.has(mechanism) ? text(record, 'summary') : ''}
                  decidable={decidable}
                  labels={{
                    show: message(locale, 'proposals.effect.show'),
                    loading: message(locale, 'proposals.effect.loading'),
                    failed: message(locale, 'proposals.effect.failed'),
                    text: message(locale, 'proposals.effect.text'),
                    preview: message(locale, 'proposals.effect.preview'),
                    dryRun: message(locale, 'proposals.effect.dryRun'),
                    dryRunQuiet: message(locale, 'proposals.effect.dryRun.quiet'),
                    approveFirst: message(locale, 'proposals.approveFirst'),
                    approve: message(locale, 'proposals.approve'),
                    reject: message(locale, 'proposals.reject'),
                    reason: message(locale, 'proposals.reason'),
                    reasonRequired: message(locale, 'proposals.reason.required'),
                  }}
                />
              </section>
            );
          })}
        </div>
      </Panel>
    </>
  );
}

/** The catalogue key naming a proposal's kind. */
function kindKey(
  kind: string,
):
  | 'proposals.type.knowledge'
  | 'proposals.type.operating_context'
  | 'proposals.type.detector'
  | 'proposals.type.configuration' {
  if (kind === 'knowledge') return 'proposals.type.knowledge';
  if (kind === 'operating_context') return 'proposals.type.operating_context';
  if (kind === 'detector') return 'proposals.type.detector';
  return 'proposals.type.configuration';
}

/** The settings patch a proposal carries, as the review component takes it. */
function payloadOf(record: unknown): Readonly<Record<string, unknown>> {
  const found: unknown = Reflect.get(Object(record), 'payload');
  return typeof found === 'object' && found !== null
    ? (found as Record<string, unknown>)
    : {};
}
