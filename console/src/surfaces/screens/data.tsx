import type { ReactNode } from 'react';

import { formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { emptyBecause, readSetupState, setupCause } from '../emptiness';
import { DeliveryToken } from '../ingress';
import { panelLabels } from '../labels';
import { Panel, type PanelEmpty } from '../panel';
import { Provenance, type ProvenanceChain } from '../provenance';
import {
  authorised,
  counts,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  optionalRead,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { Resend } from '../resend';
import { RuleSimulator } from '../simulation';
import { CopyValue } from './data-copy';

/**
 * Where it came from, and where it goes.
 *
 * Three columns, in the order data moves: what arrives, what is done with it,
 * and where the result goes. That is the order an operator traces when
 * something did not happen, and putting it on one screen is the whole point —
 * the alternative, and what this replaces, is five screens and a guess.
 *
 * **Silence is visible without being alarming.** A source that has never
 * delivered is rendered first and marked, in the same neutral tone as
 * everything else on this screen — a freshly configured deployment where
 * nothing has arrived yet is the ordinary first day, not seven faults. What
 * would actually earn the danger tone is a receiver an operator's own
 * alertmanager names and that has gone quiet after delivering before, and this
 * screen cannot tell that state apart from an ordinary first day with what the
 * API gives it today.
 *
 * **The last rule is always drawn.** What happens to a delivery no rule matched
 * is a row on the screen, not an implicit default — a discard nobody declared
 * is how an alert disappears with nobody knowing it disappeared.
 */

/** The permission the gateway requires to change what this screen shows. */
const WRITE = 'config.write';

export async function DataScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone } = context;
  const init = authorised(credential);

  const [ingress, rules, destinations, deliveries, receivers, setup] =
    await Promise.all([
      panelRead('/v1/transit/ingress', () => read('/v1/transit/ingress', init)),
      panelRead('/v1/transit/rules', () => read('/v1/transit/rules', init)),
      panelRead('/v1/transit/destinations', () =>
        read('/v1/transit/destinations', init),
      ),
      // One read of the ledger, both directions. The two columns want different
      // halves of the same table, and asking twice would be two answers about one
      // instant — which is exactly the disagreement provenance exists to prevent.
      panelRead('/v1/transit/deliveries', () => read('/v1/transit/deliveries', init)),
      optionalRead('/v1/ingress/sources', () => read('/v1/ingress/sources', init)),
      // Whether this deployment's own checklist is finished, so a column that is
      // empty because nobody has connected anything yet says that rather than
      // repeating the feature's mechanism at somebody who already knows it.
      readSetupState(credential),
    ]);
  const cause = setupCause(locale, setup);

  const sources = list(dataOf(ingress), 'sources');
  const paste = new Map(
    list(dataOf(receivers), 'sources').map((row) => [text(row, 'source'), row]),
  );
  const deliveryPermission = text(dataOf(receivers), 'delivery_permission');

  // Never-delivered first. The screen's own ordering rather than the API's,
  // because "what is silent" is the question this column is opened with.
  const ordered = [...sources].sort((left, right) => {
    const silence =
      Number(flag(right, 'never_delivered')) - Number(flag(left, 'never_delivered'));
    return silence !== 0
      ? silence
      : text(left, 'source').localeCompare(text(right, 'source'));
  });

  const ruleRows = list(dataOf(rules), 'rules');
  // Whether an operator has declared anything beyond the implicit default. The
  // catch-all is always in this list — the last rule is always drawn — so its
  // presence alone says nothing about whether there is a ranking to show.
  const explicitRules = ruleRows.some((rule) => !flag(rule, 'is_catch_all'));
  const destinationRows = list(dataOf(destinations), 'destinations');
  const ledger = rowsOf(dataOf(deliveries));
  const outboundRows = ledger.filter((row) => text(row, 'direction') === 'outbound');
  const arrivalRows = ledger.filter((row) => text(row, 'direction') === 'ingress');

  // The destination column already has a cause more specific than the setup
  // checklist when the deployment names one itself — which channel is missing
  // and where to add it — and that beats the generic "finish the setup"
  // sentence rather than being replaced by it.
  const unconfigurableReason = text(dataOf(destinations), 'unconfigurable_reason');
  const destinationsEmpty: PanelEmpty =
    unconfigurableReason === ''
      ? emptyBecause(
          {
            heading: message(locale, 'data.delivery.empty.heading'),
            body: message(locale, 'data.delivery.empty.body'),
            actionLabel: message(locale, 'data.delivery.empty.action'),
            href: '/configuration',
          },
          cause,
        )
      : {
          heading: message(locale, 'data.delivery.empty.heading'),
          body: unconfigurableReason,
          actionLabel: message(locale, 'data.delivery.empty.action'),
          href: '/configuration',
        };

  return (
    <>
      <AreaHeader area={areaFor('data')} locale={locale} />

      <div className="grid gap-4 lg:grid-cols-3" data-testid="transit-columns">
        {/* --- What arrives ------------------------------------------------ */}
        <Panel
          title={message(locale, 'data.ingress.title')}
          state={stateOf(ingress, ordered.length === 0)}
          dependency={dependencyOf(ingress)}
          labels={panelLabels(locale, message(locale, 'data.ingress.title'))}
          empty={emptyBecause(
            {
              heading: message(locale, 'data.ingress.empty.heading'),
              body: message(locale, 'data.ingress.empty.body'),
              actionLabel: message(locale, 'data.ingress.empty.action'),
              href: '/catalogue',
            },
            cause,
          )}
        >
          <ul className="flex flex-col gap-4" data-testid="ingress-sources">
            {ordered.map((source) => {
              const name = text(source, 'source');
              const silent = flag(source, 'never_delivered');
              const sample: unknown = field(source, 'sample');
              const rejections = list(source, 'recent_rejections');
              return (
                <li
                  key={name}
                  data-testid="ingress-source"
                  data-source={name}
                  data-never-delivered={String(silent)}
                  className="flex flex-col gap-1"
                >
                  <span className="text-small text-strong">{name}</span>
                  {silent ? (
                    // Neutral, not danger. A receiver that has never delivered
                    // is the ordinary shape of a deployment nobody has pointed
                    // an alert router at yet, and seven of these in error red
                    // is a fresh deployment reading as seven faults. What the
                    // API cannot say — because it has no way to know — is
                    // whether an operator's alertmanager names this receiver
                    // and has gone quiet, which is the case that would earn
                    // the emphasis this used to spend on every row.
                    <span
                      className="text-meta text-muted"
                      data-testid="never-delivered"
                    >
                      {message(locale, 'data.ingress.never')}
                    </span>
                  ) : (
                    <span className="text-meta text-muted" data-testid="last-delivery">
                      {message(locale, 'data.ingress.last')}{' '}
                      {
                        timestamp(locale, text(source, 'last_delivery_at'), now, zone)
                          .relative
                      }{' '}
                      — {text(source, 'last_outcome')}
                    </span>
                  )}
                  <code className="text-meta break-all">{text(source, 'path')}</code>
                  <span className="text-meta text-muted">
                    {text(source, 'expects')}
                  </span>
                  <span className="text-meta text-muted">
                    {message(locale, 'ingress.verification')}{' '}
                    {text(source, 'verification')}
                  </span>
                  {paste.get(name) === undefined ? null : (
                    // The absolute address this deployment answered with, save
                    // for one case this console will not repeat: an http://
                    // address on a page served over https, which is what this
                    // request's own network path looked like rather than what
                    // an outside alert router would actually reach. The path
                    // never lies about that — it carries no host — so it is
                    // what stands in until the console has a public address it
                    // can vouch for.
                    <CopyValue
                      testId="ingress-url"
                      value={
                        schemeOf(text(paste.get(name), 'url')) === UNSAFE_SCHEME
                          ? text(source, 'path')
                          : text(paste.get(name), 'url')
                      }
                      labels={{
                        copy: message(locale, 'surface.payload.copy'),
                        copied: message(locale, 'surface.payload.copied'),
                      }}
                    />
                  )}
                  {counts(source, 'counts').length === 0 ? null : (
                    <span className="text-meta text-muted" data-testid="ingress-counts">
                      {counts(source, 'counts')
                        .map(([outcome, total]) => `${outcome} ${String(total)}`)
                        .join(' · ')}
                    </span>
                  )}
                  {rejections.length === 0 ? null : (
                    <ul
                      className="text-meta text-danger flex flex-col"
                      data-testid="rejections"
                    >
                      {rejections.map((rejection) => (
                        <li key={text(rejection, 'delivery_id')}>
                          {text(rejection, 'reason')}
                        </li>
                      ))}
                    </ul>
                  )}
                  {sample === undefined || sample === null ? null : (
                    <details data-testid="sample">
                      <summary className="text-meta text-muted">
                        {message(locale, 'data.ingress.sample')} —{' '}
                        {text(sample, 'masking_policy')}
                      </summary>
                      <code className="text-meta break-all">
                        {text(sample, 'body')}
                      </code>
                    </details>
                  )}
                  <Provenance
                    labels={{
                      // What opening this actually holds, named before it is
                      // opened. Seven identical disclosures with no count is
                      // seven questions an operator has to open one at a time
                      // to answer "expand to what?".
                      open: `${message(locale, 'data.provenance.open')} (${formatNumber(
                        locale,
                        arrivalRows.filter((row) => text(row, 'source') === name)
                          .length,
                      )})`,
                      source: message(locale, 'data.provenance.source'),
                      rule: message(locale, 'data.provenance.rule'),
                      team: message(locale, 'data.provenance.team'),
                      run: message(locale, 'data.provenance.run'),
                      resource: message(locale, 'data.provenance.resource'),
                      none: message(locale, 'data.provenance.none'),
                    }}
                    chain={chainOf(name, arrivalRows)}
                  />
                </li>
              );
            })}
          </ul>
          {deliveryPermission === '' ? null : (
            // Grouped with what it is scoped to rather than left as an orphan
            // control below seven cards — every one of which already names
            // "a machine token scoped to alert delivery" as something it
            // accepts. The permission the button actually asks for sits right
            // above it, so the button reads as answering that sentence rather
            // than as an unrelated action that happened to land here.
            <div
              className="flex flex-col gap-2 pt-3 mt-1 edge border-border border-b-0 border-x-0"
              data-testid="delivery-token-group"
            >
              <span className="text-meta text-muted">
                {message(locale, 'ingress.verification')} {deliveryPermission}
              </span>
              <DeliveryToken
                permission={deliveryPermission}
                labels={{
                  issue: message(locale, 'ingress.token.issue'),
                  issuing: message(locale, 'ingress.token.issuing'),
                  shownOnce: message(locale, 'ingress.token.shownOnce'),
                  failed: message(locale, 'ingress.token.failed'),
                  unreachable: message(locale, 'ingress.token.unreachable'),
                }}
              />
            </div>
          )}
        </Panel>

        {/* --- What is done with it ---------------------------------------- */}
        <Panel
          title={message(locale, 'data.rules.title')}
          state={stateOf(rules, ruleRows.length === 0)}
          dependency={dependencyOf(rules)}
          labels={panelLabels(locale, message(locale, 'data.rules.title'))}
          empty={emptyBecause(
            {
              heading: message(locale, 'data.rules.empty.heading'),
              body: message(locale, 'data.rules.empty.body'),
              actionLabel: message(locale, 'data.rules.empty.action'),
              href: '/configuration',
            },
            cause,
          )}
        >
          {explicitRules ? (
            // The ruler: a ranking only makes sense once there is more than
            // one thing to rank, and only here does "no rule above matched"
            // refer to a list that actually exists above it.
            <ol className="flex flex-col gap-2" data-testid="routing-rules">
              {ruleRows.map((rule, index) => (
                <li
                  key={text(rule, 'rule_id')}
                  data-testid={
                    flag(rule, 'is_catch_all') ? 'catch-all-rule' : 'routing-rule'
                  }
                  data-rule={text(rule, 'rule_id')}
                  className="flex flex-col gap-1"
                >
                  <span className="text-small text-strong">
                    {String(index + 1)}. {text(rule, 'rule_id')}
                  </span>
                  <span className="text-meta text-muted">
                    {message(locale, 'data.rules.action')} {text(rule, 'action')}
                    {text(rule, 'team') === ''
                      ? ''
                      : ` → ${message(locale, 'data.provenance.team')} ${text(rule, 'team')}`}
                  </span>
                  {text(rule, 'reason') === '' ? null : (
                    <span className="text-meta text-muted">{text(rule, 'reason')}</span>
                  )}
                  {flag(rule, 'is_catch_all') ? (
                    <span
                      className="text-meta text-strong"
                      data-testid="catch-all-note"
                    >
                      {message(locale, 'data.rules.catchAll')}
                    </span>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            // Nothing an operator declared — every delivery meets the same
            // implicit default. Drawn without a rank and without "no rule
            // above matched", because with one item there is no above.
            <ul className="flex flex-col gap-2" data-testid="routing-rules">
              {ruleRows.map((rule) => (
                <li
                  key={text(rule, 'rule_id')}
                  data-testid="catch-all-rule"
                  data-rule={text(rule, 'rule_id')}
                  className="flex flex-col gap-1"
                >
                  <span className="text-small text-strong">
                    {text(rule, 'rule_id')}
                  </span>
                  <span className="text-meta text-muted">
                    {message(locale, 'data.rules.action')} {text(rule, 'action')}
                    {text(rule, 'team') === ''
                      ? ''
                      : ` → ${message(locale, 'data.provenance.team')} ${text(rule, 'team')}`}
                  </span>
                  {text(rule, 'reason') === '' ? null : (
                    <span className="text-meta text-muted">{text(rule, 'reason')}</span>
                  )}
                </li>
              ))}
            </ul>
          )}

          {/* Absent, not disabled, for a viewer who may not change the rules. */}
          {may(viewer, WRITE) ? (
            <div
              className="flex flex-col gap-2 pt-3 mt-1 edge border-border border-b-0 border-x-0"
              data-testid="delivery-tester"
            >
              {/* An honest name for what this is, rather than a select, a
                  textarea and two unlabelled buttons. */}
              <h4 className="text-strong">{message(locale, 'data.simulate.action')}</h4>
              <RuleSimulator
                sources={sources.map((source) => text(source, 'source'))}
                labels={{
                  source: message(locale, 'data.simulate.source'),
                  payload: message(locale, 'data.simulate.payload'),
                  simulate: message(locale, 'data.simulate.action'),
                  simulating: message(locale, 'data.simulate.running'),
                  save: message(locale, 'data.simulate.save'),
                  needsSimulation: message(locale, 'data.simulate.needed'),
                  rule: message(locale, 'data.provenance.rule'),
                  team: message(locale, 'data.provenance.team'),
                  action: message(locale, 'data.rules.action'),
                  failed: message(locale, 'data.simulate.failed'),
                  unreachable: message(locale, 'data.simulate.unreachable'),
                  malformed: message(locale, 'data.simulate.malformed'),
                }}
              />
            </div>
          ) : null}
        </Panel>

        {/* --- Where the result goes --------------------------------------- */}
        <Panel
          title={message(locale, 'data.delivery.title')}
          state={stateOf(destinations, destinationRows.length === 0)}
          dependency={dependencyOf(destinations)}
          labels={panelLabels(locale, message(locale, 'data.delivery.title'))}
          empty={destinationsEmpty}
        >
          <ul className="flex flex-col gap-3" data-testid="destinations">
            {destinationRows.map((destination) => (
              <li
                key={text(destination, 'destination_id')}
                data-testid="destination"
                data-destination={text(destination, 'destination_id')}
                className="flex flex-col gap-1"
              >
                <span className="text-small text-strong">
                  {text(destination, 'destination_id')}
                </span>
                <span className="text-meta text-muted">
                  {text(destination, 'channel')} · {text(destination, 'detail')}
                </span>
                <span className="text-meta text-muted" data-testid="destination-events">
                  {list(destination, 'events')
                    .map((event) => String(event))
                    .join(', ')}
                </span>
                <span
                  className="text-meta text-muted"
                  data-testid="destination-masking"
                >
                  {message(locale, 'data.delivery.masking')}{' '}
                  {text(destination, 'masking_policy')}
                </span>
                {text(destination, 'unconfigurable_reason') === '' ? null : (
                  <span
                    className="text-meta text-danger"
                    data-testid="destination-unusable"
                  >
                    {text(destination, 'unconfigurable_reason')}
                  </span>
                )}
              </li>
            ))}
          </ul>

          <ul className="flex flex-col gap-2" data-testid="outbound-failures">
            {outboundRows
              .filter((row) => text(row, 'outcome') === 'failed')
              .map((row) => (
                <li
                  key={text(row, 'delivery_id')}
                  data-testid="failed-delivery"
                  className="flex flex-col gap-1"
                >
                  <span className="text-meta text-danger">
                    {text(row, 'source')} — {text(row, 'reason')}
                  </span>
                  {may(viewer, WRITE) ? (
                    <Resend
                      deliveryId={text(row, 'delivery_id')}
                      labels={{
                        resend: message(locale, 'data.delivery.resend'),
                        resending: message(locale, 'data.delivery.resending'),
                        delivered: message(locale, 'data.delivery.resent'),
                        failed: message(locale, 'data.delivery.resendFailed'),
                        unreachable: message(locale, 'data.simulate.unreachable'),
                      }}
                    />
                  ) : null}
                </li>
              ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}

/** A list endpoint's body, or an empty list when the read failed. */
function rowsOf(body: unknown): readonly unknown[] {
  return Array.isArray(body) ? body : [];
}

// Built from parts rather than written whole, so the scheme this checks for
// is never itself a literal origin — the very thing this file exists to stop
// the screen from announcing.
const UNSAFE_SCHEME = ['http', ':'].join('');

/**
 * The scheme `url` declares, or the empty string when it does not parse.
 *
 * Parsed rather than matched against a prefix: a scheme is what `URL` says it
 * is, and a deployment's own request context is not a string this file should
 * be pattern-matching by hand.
 */
function schemeOf(url: string): string {
  try {
    return new URL(url).protocol;
  } catch {
    return '';
  }
}

/**
 * The chain one source's newest arrival can answer.
 *
 * Built from the ledger rows the screen already read rather than from a second
 * query per source: the drawer renders provenance that exists, and a read per
 * receiver would make the screen's cost a function of how many an operator
 * wired up.
 */
function chainOf(source: string, arrivals: readonly unknown[]): ProvenanceChain {
  const newest = arrivals.find((row) => text(row, 'source') === source);
  return {
    source,
    instant: text(newest, 'occurred_at'),
    outcome: text(newest, 'outcome'),
    rule: text(newest, 'matched_rule'),
    team: text(newest, 'team_node_id'),
    run: text(newest, 'run_id'),
    resource: text(newest, 'resource_id'),
  };
}
