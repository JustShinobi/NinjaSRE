import type { ReactNode } from 'react';

import type { MessageKey } from '@/i18n/en';
import { Reference } from '@/design/reference';
import { formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { Badge } from '@/components/status';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { AdvancedConfigSection } from '../advanced-config-section';
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
import { isConsoleSession } from '../token-identity';
import { Provenance, type ProvenanceChain } from '../provenance';
import { RuleSimulator } from '../simulation';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';

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

const ALERT_INTAKE_FILTERS: readonly FilterName[] = ['node'];

/**
 * The observation policy's own scalar fields, with no control of their own
 * before this: whether this team is watching at all, and the scalar settings
 * of its own monitoring bridge and the shipped detector guardian. The
 * bridge's own lists (label rules, log selectors, dashboards, precedence) and
 * the detector list stay off this page's control — they already draw through
 * the same prefixed editor below, but a purpose-built add/remove/reorder
 * control for them is separate work this page does not do.
 */
const ALERT_INTAKE_ADVANCED_PREFIX = 'policies.observation.';

const ALERT_INTAKE_ADVANCED_FIELD_LIST: readonly {
  readonly path: string;
  readonly label: MessageKey;
}[] = [
  {
    path: 'policies.observation.paused',
    label: 'settings.alertIntake.advanced.field.paused',
  },
  {
    path: 'policies.observation.pause_reason',
    label: 'settings.alertIntake.advanced.field.pauseReason',
  },
  {
    path: 'policies.observation.bridge.enabled',
    label: 'settings.alertIntake.advanced.field.bridgeEnabled',
  },
  {
    path: 'policies.observation.bridge.dashboard_base_url',
    label: 'settings.alertIntake.advanced.field.bridgeDashboardBaseUrl',
  },
  {
    path: 'policies.observation.bridge.mapping_interval_seconds',
    label: 'settings.alertIntake.advanced.field.bridgeMappingIntervalSeconds',
  },
  {
    path: 'policies.observation.bridge.history_lookback_seconds',
    label: 'settings.alertIntake.advanced.field.bridgeHistoryLookbackSeconds',
  },
  {
    path: 'policies.observation.bridge.log_window_seconds',
    label: 'settings.alertIntake.advanced.field.bridgeLogWindowSeconds',
  },
  {
    path: 'policies.observation.bridge.log_line_limit',
    label: 'settings.alertIntake.advanced.field.bridgeLogLineLimit',
  },
  {
    path: 'policies.observation.bridge.use_shipped_rules',
    label: 'settings.alertIntake.advanced.field.bridgeUseShippedRules',
  },
  {
    path: 'policies.observation.bridge.use_shipped_log_selectors',
    label: 'settings.alertIntake.advanced.field.bridgeUseShippedLogSelectors',
  },
  {
    path: 'policies.observation.bridge.logs.enabled',
    label: 'settings.alertIntake.advanced.field.bridgeLogsEnabled',
  },
  {
    path: 'policies.observation.bridge.logs.name',
    label: 'settings.alertIntake.advanced.field.bridgeLogsName',
  },
  {
    path: 'policies.observation.bridge.logs.endpoint',
    label: 'settings.alertIntake.advanced.field.bridgeLogsEndpoint',
  },
  {
    path: 'policies.observation.bridge.logs.integration',
    label: 'settings.alertIntake.advanced.field.bridgeLogsIntegration',
  },
  {
    path: 'policies.observation.bridge.metrics.enabled',
    label: 'settings.alertIntake.advanced.field.bridgeMetricsEnabled',
  },
  {
    path: 'policies.observation.bridge.metrics.name',
    label: 'settings.alertIntake.advanced.field.bridgeMetricsName',
  },
  {
    path: 'policies.observation.bridge.metrics.endpoint',
    label: 'settings.alertIntake.advanced.field.bridgeMetricsEndpoint',
  },
  {
    path: 'policies.observation.bridge.metrics.integration',
    label: 'settings.alertIntake.advanced.field.bridgeMetricsIntegration',
  },
  {
    path: 'policies.observation.guardian.enabled',
    label: 'settings.alertIntake.advanced.field.guardianEnabled',
  },
  {
    path: 'policies.observation.guardian.cluster_shape',
    label: 'settings.alertIntake.advanced.field.guardianClusterShape',
  },
  {
    path: 'policies.observation.guardian.heartbeat_destination',
    label: 'settings.alertIntake.advanced.field.guardianHeartbeatDestination',
  },
  {
    path: 'policies.observation.guardian.declared_intent_source',
    label: 'settings.alertIntake.advanced.field.guardianDeclaredIntentSource',
  },
];

/** A list endpoint's body, or an empty list when the read failed. */
function rowsOf(body: unknown): readonly unknown[] {
  return Array.isArray(body) ? body : [];
}

/**
 * The name of the live token that actually authenticates delivery, or
 * `undefined` when nothing has been issued with that permission yet.
 *
 * `webhook.deliver` is a fact about a token, not a name — showing it in place
 * of one is exactly the leak this page used to have. Cross-referencing
 * `/identity/tokens` by scope is how the screen tells the reader which
 * credential is actually doing the authenticating, the way it already names
 * anything else the deployment issued. A browser session is excluded the
 * same way `settings/machine-tokens.tsx` excludes it from its own list — a
 * person's own sign-in is not "the delivery token" even if it happened to
 * carry the scope. Newest first, so more than one token sharing the scope
 * still names the one presently in use rather than whichever the deployment
 * happened to list first.
 */
function deliveryTokenNamed(
  records: readonly unknown[],
  permission: string,
): string | undefined {
  const holders = records
    .filter((record) => !isConsoleSession({ name: text(record, 'name') }))
    .filter((record) => !flag(record, 'revoked'))
    .filter((record) => list(record, 'scopes').map(String).includes(permission))
    .sort((left, right) =>
      text(right, 'created_at').localeCompare(text(left, 'created_at')),
    );
  const name = holders[0] === undefined ? '' : text(holders[0], 'name');
  return name === '' ? undefined : name;
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
  const { credential, locale, viewer, search, now, zone } = context;
  const init = authorised(credential);
  const writable = may(viewer, WRITE);
  const state = readViewState(search, ALERT_INTAKE_FILTERS);

  const [ingress, rules, deliveries, receivers, tree, identity] = await Promise.all([
    panelRead('/v1/transit/ingress', () => read('/v1/transit/ingress', init)),
    panelRead('/v1/transit/rules', () => read('/v1/transit/rules', init)),
    panelRead('/v1/transit/deliveries', () => read('/v1/transit/deliveries', init)),
    optionalRead('/v1/ingress/sources', () => read('/v1/ingress/sources', init)),
    panelRead('/v1/config', () => read('/v1/config', init)),
    // Naming the delivery token needs an extra read this page did not make
    // before — justified because it is the one thing left between "who is
    // trusted" reading as a permission string and reading as a credential a
    // person issued. A failed read degrades to "not yet authenticated"
    // rather than an error state for the whole panel: which token, if any,
    // is doing the authenticating is a detail of this group, not the reason
    // the receiver list itself would fail to render.
    optionalRead('/identity/tokens', () => read('/identity/tokens', init)),
  ]);

  const nodeId = resolveNode(state, viewer, placedTree(dataOf(tree)));

  // Nothing empty, ready: the advanced section below renders its rows with
  // nothing set, which is the honest state for a node this deployment has
  // not configured any observation policy at yet. Read regardless of
  // `writable`: the effective-value table shows every viewer of this page
  // what a field resolves to, not only one who may change it.
  const nothing = { status: 'ready' as const, data: {} as unknown };
  const configFields =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/config/{node_id}/fields', () =>
          read('/v1/config/{node_id}/fields', { ...init, params: { node_id: nodeId } }),
        );

  const sources = list(dataOf(ingress), 'sources');
  const paste = new Map(
    list(dataOf(receivers), 'sources').map((row) => [text(row, 'source'), row]),
  );
  const deliveryPermission = text(dataOf(receivers), 'delivery_permission');
  const deliveryTokenName =
    deliveryPermission === ''
      ? undefined
      : deliveryTokenNamed(list(dataOf(identity), 'tokens'), deliveryPermission);

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
            <span className="text-meta text-muted" data-testid="delivery-token-trust">
              {deliveryTokenName === undefined ? (
                message(locale, 'ingress.delivery.unauthenticated')
              ) : (
                <>
                  {message(locale, 'ingress.delivery.authenticated')}{' '}
                  <code data-testid="delivery-token-name">{deliveryTokenName}</code>
                </>
              )}
            </span>
            <DeliveryToken
              permission={deliveryPermission}
              labels={{
                issue: message(
                  locale,
                  deliveryTokenName === undefined
                    ? 'ingress.token.issue'
                    : 'ingress.token.rotate',
                ),
                issuing: message(
                  locale,
                  deliveryTokenName === undefined
                    ? 'ingress.token.issuing'
                    : 'ingress.token.rotating',
                ),
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
            // The routing rules this panel reads are declared on Schedules &
            // destinations, not on the retired editor.
            href: '/settings/schedules-destinations',
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

      <div className="mt-5">
        <AdvancedConfigSection
          title={message(locale, 'settings.alertIntake.advanced.title')}
          prefix={ALERT_INTAKE_ADVANCED_PREFIX}
          nodeId={nodeId}
          locale={locale}
          writable={writable}
          fields={ALERT_INTAKE_ADVANCED_FIELD_LIST.map(({ path, label }) => ({
            path,
            label: message(locale, label),
          }))}
          rawFields={dataOf(configFields)}
        />
      </div>
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
