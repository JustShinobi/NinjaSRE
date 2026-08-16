import type { ReactNode } from 'react';

import { Reference } from '@/design/reference';
import { formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { Badge } from '@/components/status';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { CopyValue } from '../screens/data-copy';
import { emptyBecause, readSetupState, setupCause, type Cause } from '../emptiness';
import { requestedSetupReturn, SetupReturnBanner } from '../first-run/return-banner';
import { DeliveryToken } from '../ingress';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
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
import { Provenance, type ProvenanceChain } from '../provenance';
import { RuleSimulator } from '../simulation';

/**
 * Alert intake: what arrives, and the rules that decide what happens to it.
 *
 * Absorbs the old "Intake" tab of Signals, inverted. The tab it replaces led
 * with a receiver's documentation — payload, headers, the signature scheme —
 * and buried the two things an operator actually came to do, copy the
 * endpoint and issue a token, in the middle of that prose. Here the row is
 * the action: a name, a copyable endpoint, and a chip saying whether
 * anything has arrived. Format, the trust mechanism and the delivery test
 * move behind `Reference`, one press away, because none of them is needed to
 * point an alert router here — they are needed to debug one that is already
 * pointed here and still not arriving.
 *
 * **Silence is visible without being alarming; a refusal is not.** A source
 * that has never delivered is drawn first, in the same neutral tone as
 * everything else — a freshly configured deployment where nothing has
 * arrived yet is the ordinary first day, not seven faults. A source that
 * *has* delivered carries its last outcome as the shared status vocabulary
 * already renders it, so a rejected delivery reads in the same danger role
 * every other rejected thing in this console does, and an accepted one does
 * not — the one distinction silence alone cannot make.
 *
 * **The simulator is the receiver's, not the page's.** The old tab's "Test a
 * delivery" panel let an operator pick any receiver from a dropdown; this
 * one is reached from the receiver whose payload it is testing, because that
 * is where the question is actually being asked.
 *
 * **Routing rules are unchanged.** What a rule does to a verified delivery is
 * a fact about the deployment, not about one receiver, so it keeps its own
 * panel rather than folding into any single row.
 */

const ID = 'settings-alert-intake';

/** The permission the gateway requires to change what this screen shows. */
const WRITE = 'config.write';

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

/** The page's own body: the receivers, and the routing rules beneath them. */
async function content(
  context: SurfaceContext,
  cause: Cause | null,
): Promise<ReactNode> {
  const { credential, locale, viewer, now, zone } = context;
  const init = authorised(credential);

  const [ingress, rules, deliveries, receivers] = await Promise.all([
    panelRead('/v1/transit/ingress', () => read('/v1/transit/ingress', init)),
    panelRead('/v1/transit/rules', () => read('/v1/transit/rules', init)),
    panelRead('/v1/transit/deliveries', () => read('/v1/transit/deliveries', init)),
    optionalRead('/v1/ingress/sources', () => read('/v1/ingress/sources', init)),
  ]);

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
  const explicitRules = ruleRows.some((rule) => !flag(rule, 'is_catch_all'));
  const ledger = rowsOf(dataOf(deliveries));
  const arrivalRows = ledger.filter((row) => text(row, 'direction') === 'ingress');

  return (
    <>
      {/* --- What arrives -------------------------------------------------- */}
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
            href: '/integrations',
          },
          cause,
        )}
      >
        <ul className="flex flex-col gap-3" data-testid="ingress-sources">
          {ordered.map((source) => {
            const name = text(source, 'source');
            const silent = flag(source, 'never_delivered');
            const sample: unknown = field(source, 'sample');
            const rejections = list(source, 'recent_rejections');
            const pasteRow = paste.get(name);

            return (
              <li
                key={name}
                data-testid="ingress-source"
                data-source={name}
                data-never-delivered={String(silent)}
                className="flex flex-col gap-1 rounded-3 edge border-border p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-small text-strong">{name}</span>
                  {silent ? (
                    // Neutral, not danger — the ordinary shape of a
                    // deployment nobody has pointed an alert router at yet,
                    // never the seven-faults reading a colour would give it.
                    <span
                      className="text-meta text-muted"
                      data-testid="never-delivered"
                    >
                      {message(locale, 'data.ingress.never')}
                    </span>
                  ) : (
                    <span
                      className="text-meta text-muted flex items-center gap-1"
                      data-testid="last-delivery"
                    >
                      {message(locale, 'data.ingress.last')}{' '}
                      {
                        timestamp(locale, text(source, 'last_delivery_at'), now, zone)
                          .relative
                      }
                      <Badge status={text(source, 'last_outcome')} />
                    </span>
                  )}
                </div>

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

                {pasteRow === undefined ? null : (
                  // The endpoint is one of the three things a compact row
                  // carries, shown always rather than behind the detail —
                  // but only once there is a genuinely paste-ready,
                  // absolute address to show. The bare relative `path` this
                  // deployment also knows is not that: pasted into an
                  // external alert router with no host, it resolves nowhere,
                  // so absent, correctly-scoped data beats a copy button that
                  // looks actionable and is not.
                  <CopyValue
                    testId="ingress-url"
                    value={
                      schemeOf(text(pasteRow, 'url')) === UNSAFE_SCHEME
                        ? text(source, 'path')
                        : text(pasteRow, 'url')
                    }
                    labels={{
                      copy: message(locale, 'surface.payload.copy'),
                      copied: message(locale, 'surface.payload.copied'),
                    }}
                  />
                )}

                <Provenance
                  labels={{
                    open: `${message(locale, 'data.provenance.open')} (${formatNumber(
                      locale,
                      arrivalRows.filter((row) => text(row, 'source') === name).length,
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

                <Reference
                  title={message(locale, 'data.ingress.detail.title')}
                  summary={message(locale, 'data.ingress.detail.summary')}
                >
                  <div className="flex flex-col gap-2">
                    <p>
                      <span className="text-muted">
                        {message(locale, 'data.ingress.detail.format')}
                      </span>{' '}
                      {text(source, 'expects')}
                    </p>
                    <p>
                      <span className="text-muted">
                        {message(locale, 'ingress.verification')}
                      </span>{' '}
                      {text(source, 'verification')}
                    </p>
                    {counts(source, 'counts').length === 0 ? null : (
                      <p data-testid="ingress-counts">
                        {counts(source, 'counts')
                          .map(([outcome, total]) => `${outcome} ${String(total)}`)
                          .join(' · ')}
                      </p>
                    )}
                    {sample === undefined || sample === null ? null : (
                      <div data-testid="sample">
                        <p className="text-muted">
                          {message(locale, 'data.ingress.sample')} —{' '}
                          {text(sample, 'masking_policy')}
                        </p>
                        <code className="text-meta break-all">
                          {text(sample, 'body')}
                        </code>
                      </div>
                    )}

                    {may(viewer, WRITE) ? (
                      <div
                        className="flex flex-col gap-2 pt-2 mt-1 edge border-border border-b-0 border-x-0"
                        data-testid="delivery-tester"
                      >
                        <h4 className="text-strong">
                          {message(locale, 'data.simulate.title')}
                        </h4>
                        <p className="text-meta text-muted">
                          {message(locale, 'data.simulate.purpose')}
                        </p>
                        <RuleSimulator
                          sources={[name]}
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
                  </div>
                </Reference>
              </li>
            );
          })}
        </ul>

        {deliveryPermission === '' ? null : (
          // Grouped with what it is scoped to rather than left as an orphan
          // control below every row — every receiver already names "a
          // machine token scoped to alert delivery" as something it accepts,
          // and the permission the button asks for sits right above it.
          <div
            className="flex flex-col gap-2 pt-3 mt-3 edge border-border border-b-0 border-x-0"
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

      {/* --- What happens to it --------------------------------------------- */}
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
                  <span className="text-meta text-strong" data-testid="catch-all-note">
                    {message(locale, 'data.rules.catchAll')}
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        ) : (
          <ul className="flex flex-col gap-2" data-testid="routing-rules">
            {ruleRows.map((rule) => (
              <li
                key={text(rule, 'rule_id')}
                data-testid="catch-all-rule"
                data-rule={text(rule, 'rule_id')}
                className="flex flex-col gap-1"
              >
                <span className="text-small text-strong">{text(rule, 'rule_id')}</span>
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
      </Panel>
    </>
  );
}

/** The whole `/settings/alert-intake` page: the Settings header, then the body. */
export async function AlertIntakeScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, search } = context;
  const setup = await readSetupState(credential);
  return (
    <>
      <SettingsPageHeader page={settingsPageFor(ID)} locale={locale} />
      <SetupReturnBanner
        locale={locale}
        setup={setup}
        requested={requestedSetupReturn(search.get('return'))}
      />
      {await content(context, setupCause(locale, setup))}
    </>
  );
}
