import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { formatNumber } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { timestamp } from '@/i18n/format';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import { KillSwitchControl } from '@/shell/stop';
import type { SurfaceContext } from '../context';
import { AutonomyEditor, type EditableRule } from '../autonomy-editor';
import { panelLabels } from '../labels';
import { OverrideEditor, type ActiveOverride } from '../override-editor';
import { Panel } from '../panel';
import { postureLabels } from '../postures';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  number,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';

/**
 * What this deployment may do on its own, and why.
 *
 * The rules table is the whole screen and it is read in **resolution order** —
 * least specific first — because that is the order the deployment reads them in
 * and an operator checking "which of these wins" should not have to reconstruct
 * the precedence from the scopes.
 *
 * The footer is not decoration and stays whatever the table holds. Absence of a
 * rule resolves to propose-only, and an operator reading an empty table has to
 * know whether empty means "anything goes" or "nothing happens without me".
 * Guessing the permissive answer is the one direction this must never be wrong
 * in, so the screen says it rather than implying it.
 *
 * The bounds beside it are the four no level overrides. They are shown even
 * when the table is full, because "restarting is autonomous here" and "and
 * nothing runs between 01:00 and 04:00" are both true and an operator who read
 * only the first would be surprised at two in the morning.
 *
 * Every one of those readings is *at a node*, so the node is resolved before
 * anything is asked for. A deployment with no organisation tree yet resolves to
 * none, and then nothing is asked at all: a policy request with no subject is a
 * path with a brace still in it, which the client refuses and which used to take
 * this route down before an operator had any way to choose a node.
 *
 * **One empty state, not three.** Reading no rules and reading no bounds used to
 * be reported by three panels in the same words, and a reader could not tell
 * from that repetition whether the deployment held nothing or the console had
 * asked three times and heard the same "nothing" three times. Now the rules
 * table's own panel is the one place that says so, in the panel's ordinary
 * empty state — and directly beneath it, for a viewer who may write, sits the
 * same editor a real rule would use, seeded with one deployment-wide row at the
 * safest level. Creating the first rule is choosing that row's level and
 * saving it, not a trip to Configuration to work out how. The bounds panel,
 * which would otherwise say the identical "nothing recorded" a second time,
 * is left out of the page entirely when both it and the rules table are
 * genuinely empty — it still appears, as it always did, the moment either one
 * holds something, including a failure of its own read.
 *
 * **The same stop, in the place that governs it.** The topbar's emergency stop
 * and this screen's bounds are one axis, not two: what the switch does *is* a
 * bound, reported here from the same `bounds.stopped` the switch sets. Rather
 * than restate that in the screen's own words, the stopped row renders the
 * shell's own kill-switch control, so resuming automation is available exactly
 * where an operator is already looking at what automation may do.
 *
 * **The vocabulary is stated, not assumed.** A rule, a bound and an override
 * are used throughout this page before anything else on it explains them, so
 * three lines at the top say what each one is — the same three words the rest
 * of the screen already uses, not a fourth set invented for the glossary.
 *
 * **An override is revoked by clicking it, never by typing its name.** Every
 * override this node's bounds report — the informational row above and the
 * revocable one beside it — is resolved once, here, into `activeOverrides`,
 * so a reader sees the same expiry either place and a click always names
 * something the deployment can actually find; there is nothing to remember
 * or mistype.
 */

export const AUTONOMY_FILTERS: readonly FilterName[] = ['node'];

/** The permission that decides whether the editor is on the page at all. */
const WRITE = 'config.write';

/** The levels the deployment declares, least autonomous first. */
const LEVELS = ['propose_only', 'act_on_low_risk', 'act_and_report', 'act_silently'];

/** The levels an override may raise a scope to. Overrides never grant silence. */
const OVERRIDE_LEVELS = ['propose_only', 'act_on_low_risk', 'act_and_report'];

/** Least specific first, which is the order resolution considers them in. */
const SCOPE_ORDER = [
  'deployment',
  'team',
  'resource_kind',
  'labels',
  'capability',
  'resource',
  'capability_resource',
];

/**
 * Where `act_on_low_risk` draws its line when nobody has said otherwise.
 * Mirrors the deployment's own default (`config/constants/autonomy.py`,
 * `DEFAULT_RISK_BOUND`) rather than inventing a console-side opinion about it.
 */
const DEFAULT_RISK_BOUND = 'low';

/**
 * What an operator edits when there is no rule yet: one row, scoped to the
 * whole deployment, at the safest level. Saving it *is* creating the first
 * rule — there is no separate "add a rule" affordance to reach for, because
 * this row already is the form.
 */
const FIRST_RULE: EditableRule = {
  ruleId: 'deployment',
  scope: 'deployment',
  matcher: '—',
  level: LEVELS[0] ?? 'propose_only',
  riskBound: DEFAULT_RISK_BOUND,
  record: {
    scope: { kind: 'deployment' },
    level: LEVELS[0] ?? 'propose_only',
    risk_bound: DEFAULT_RISK_BOUND,
  },
};

/** The phrase a scope reads as, assembled from the fields the API sends. */
function matcherOf(scope: unknown): string {
  const kind = text(scope, 'kind');
  if (kind === 'deployment') return '—';
  if (kind === 'team') return text(scope, 'team_node_id');
  if (kind === 'resource_kind') return text(scope, 'resource_kind');
  if (kind === 'labels') {
    const labels = field(scope, 'labels');
    if (typeof labels !== 'object' || labels === null) return '—';
    return Object.entries(labels)
      .map(([name, value]) => `${name}=${String(value)}`)
      .sort()
      .join(', ');
  }
  if (kind === 'capability') return text(scope, 'capability');
  if (kind === 'resource') return text(scope, 'resource_id');
  return `${text(scope, 'capability')} on ${text(scope, 'resource_id')}`;
}

function specificityOf(rule: unknown): number {
  const found = SCOPE_ORDER.indexOf(text(field(rule, 'scope'), 'kind'));
  return found === -1 ? SCOPE_ORDER.length : found;
}

export async function AutonomyScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search, now, zone } = context;
  const state = readViewState(search, AUTONOMY_FILTERS);
  const init = authorised(credential);

  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const nodeId = resolveNode(state, viewer, placedTree(dataOf(tree)));

  // Nothing empty, ready: the rules panel then renders its own empty state,
  // which says there is no policy here and offers the way to make one.
  const nothing = { status: 'ready' as const, data: {} as unknown };

  const policy =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/autonomy/policy/{node_id}', () =>
          read('/v1/autonomy/policy/{node_id}', {
            ...init,
            params: { node_id: nodeId },
          }),
        );
  const bounds =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/autonomy/policy/{node_id}/bounds', () =>
          read('/v1/autonomy/policy/{node_id}/bounds', {
            ...init,
            params: { node_id: nodeId },
          }),
        );

  const rules = [...list(dataOf(policy), 'rules')].sort(
    (left, right) => specificityOf(left) - specificityOf(right),
  );
  const simulated = flag(dataOf(policy), 'dry_run');
  const stopped = flag(dataOf(bounds), 'stopped');
  const freezes = list(dataOf(bounds), 'freezes');
  const budgets = list(dataOf(bounds), 'budgets');
  const overrides = list(dataOf(bounds), 'overrides');
  const writable = may(viewer, WRITE);

  // Resolved once, here, where the locale and the clock are — the override
  // editor is a client component with neither. Feeds both the read-only row
  // below and the revoke list beside it, so the two can never format the same
  // override's expiry two different ways.
  const activeOverrides: readonly ActiveOverride[] = overrides.map((override) => {
    const expires = timestamp(locale, text(override, 'expires_at'), now, zone);
    return {
      name: text(override, 'name'),
      level: text(override, 'level'),
      expiresIso: expires.iso,
      expiresRelative: expires.relative,
      expiresAbsolute: expires.absolute,
      reason: text(override, 'reason'),
      grantedBy: text(override, 'granted_by'),
    };
  });

  const rulesEmpty = rules.length === 0;
  const boundsEmpty =
    !stopped && freezes.length === 0 && budgets.length === 0 && overrides.length === 0;
  // The bounds panel drops out of the page only when it would otherwise repeat
  // the rules panel's own "nothing recorded" — never when it is reporting a
  // failure of its own, which is worth a reader's attention on its own terms.
  const showBounds =
    nodeId !== '' &&
    (policy.status === 'error' ||
      bounds.status === 'error' ||
      !(rulesEmpty && boundsEmpty));

  // Every rule carried back as the deployment sent it, so a save changes the
  // level and nothing else. A console that rebuilt the record from the columns
  // it renders would drop whatever it does not render. With no rule recorded
  // yet, the editor is seeded with one deployment-wide row instead of an empty
  // list, so there is something to choose a level for and save.
  const editable: readonly EditableRule[] =
    rules.length > 0
      ? rules.map((rule, position) => {
          const scope = field(rule, 'scope');
          return {
            ruleId:
              text(rule, 'rule_id') || `${text(scope, 'kind')}-${String(position)}`,
            scope: text(scope, 'kind'),
            matcher: matcherOf(scope),
            level: text(rule, 'level'),
            riskBound: text(rule, 'risk_bound'),
            record: rule as Readonly<Record<string, unknown>>,
          };
        })
      : [FIRST_RULE];

  const configurationHref =
    nodeId === ''
      ? '/configuration'
      : `/configuration?node=${encodeURIComponent(nodeId)}`;

  return (
    <>
      <AreaHeader
        area={areaFor('autonomy')}
        locale={locale}
        // No crumb for a deployment that resolved to no node: a breadcrumb
        // whose last step is blank reads as a page that lost its subject.
        nested={nodeId === '' ? [] : [{ label: nodeId }]}
      />

      {/* What the rest of the page assumes an operator already knows. Three
          lines, one per term, because the page uses all three below without
          ever pausing to define them otherwise. */}
      <div
        data-testid="autonomy-glossary"
        className="flex flex-col gap-1 text-meta text-muted mb-5 max-w-prose"
      >
        <p>{message(locale, 'autonomy.glossary.rule')}</p>
        <p>{message(locale, 'autonomy.glossary.bound')}</p>
        <p>{message(locale, 'autonomy.glossary.override')}</p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0">
          <Panel
            title={message(locale, 'autonomy.rules.title')}
            state={stateOf(policy, rulesEmpty)}
            dependency={dependencyOf(policy)}
            labels={panelLabels(locale, message(locale, 'autonomy.rules.title'))}
            empty={{
              heading: message(locale, 'autonomy.empty.heading'),
              body: message(locale, 'autonomy.empty.body'),
              actionLabel: message(locale, 'autonomy.empty.action'),
              href: configurationHref,
            }}
          >
            <div className="w-full overflow-x-auto">
              <table className="w-full text-small">
                <caption className="sr-only">
                  {message(locale, 'autonomy.rules.title')}
                </caption>
                <thead>
                  <tr>
                    {[
                      message(locale, 'autonomy.column.scope'),
                      message(locale, 'autonomy.column.matcher'),
                      message(locale, 'autonomy.column.level'),
                      message(locale, 'autonomy.column.risk'),
                    ].map((header) => (
                      <th
                        key={header}
                        scope="col"
                        className="text-left text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
                      >
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule, position) => {
                    const scope = field(rule, 'scope');
                    const level = text(rule, 'level');
                    return (
                      <tr
                        key={`${text(scope, 'kind')}-${String(position)}`}
                        data-testid="autonomy-rule"
                        data-level={level}
                      >
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                          {text(scope, 'kind')}
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0 break-all">
                          {matcherOf(scope)}
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                          <Badge status={level} />
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                          {level === 'act_on_low_risk' ? text(rule, 'risk_bound') : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
          {rules.length > 0 ? (
            <p data-testid="autonomy-footer" className="text-meta text-muted mt-3">
              {message(locale, 'autonomy.footer')}
            </p>
          ) : null}
          {simulated ? (
            <p data-testid="autonomy-dry-run" className="text-meta text-muted mt-2">
              {message(locale, 'autonomy.dry_run')}
            </p>
          ) : null}

          {/* Absent, not disabled, for a viewer who may not write. */}
          {writable && nodeId !== '' ? (
            <div className="mt-5">
              <Panel
                title={message(locale, 'autonomy.editor.save')}
                state={stateOf(policy, false)}
                dependency={dependencyOf(policy)}
                labels={panelLabels(locale, message(locale, 'autonomy.editor.save'))}
                empty={{
                  heading: message(locale, 'autonomy.empty.heading'),
                  body: message(locale, 'autonomy.empty.body'),
                  actionLabel: message(locale, 'autonomy.empty.action'),
                  href: configurationHref,
                }}
              >
                <AutonomyEditor
                  nodeId={nodeId}
                  rules={editable}
                  levels={LEVELS}
                  levelLabels={postureLabels(locale, LEVELS)}
                  dryRun={simulated}
                  labels={{
                    level: message(locale, 'autonomy.editor.level'),
                    preview: message(locale, 'autonomy.editor.preview'),
                    previewing: message(locale, 'autonomy.editor.previewing'),
                    explain: message(locale, 'autonomy.editor.explain'),
                    explaining: message(locale, 'autonomy.editor.explaining'),
                    explainCapability: message(locale, 'autonomy.editor.capability'),
                    explainResource: message(locale, 'autonomy.editor.resource'),
                    save: message(locale, 'autonomy.editor.save'),
                    saving: message(locale, 'autonomy.editor.saving'),
                    saved: message(locale, 'autonomy.editor.saved'),
                    failed: message(locale, 'autonomy.editor.failed'),
                    unreachable: message(locale, 'autonomy.editor.unreachable'),
                    previewFirst: message(locale, 'autonomy.editor.previewFirst'),
                    considered: message(locale, 'autonomy.editor.considered'),
                    changed: message(locale, 'autonomy.editor.changed'),
                    newlyAutonomous: message(locale, 'autonomy.editor.newlyAutonomous'),
                    nothingChanges: message(locale, 'autonomy.editor.nothingChanges'),
                    dryRunOn: message(locale, 'autonomy.editor.dryRunOn'),
                    dryRunOff: message(locale, 'autonomy.editor.dryRunOff'),
                    dryRunBanner: message(locale, 'autonomy.editor.dryRunBanner'),
                    decision: message(locale, 'autonomy.editor.decision'),
                    winningRule: message(locale, 'autonomy.editor.winningRule'),
                  }}
                />
              </Panel>
            </div>
          ) : null}
        </div>

        <div className="min-w-0 flex flex-col gap-5">
          {showBounds ? (
            <Panel
              title={message(locale, 'autonomy.bounds.title')}
              state={stateOf(bounds, boundsEmpty)}
              dependency={dependencyOf(bounds)}
              labels={panelLabels(locale, message(locale, 'autonomy.bounds.title'))}
              empty={{
                heading: message(locale, 'autonomy.empty.heading'),
                body: message(locale, 'autonomy.empty.body'),
                actionLabel: message(locale, 'autonomy.empty.action'),
                href: configurationHref,
              }}
            >
              <dl className="flex flex-col gap-2 text-small">
                {stopped ? (
                  <div
                    className="flex flex-wrap items-center gap-3"
                    data-testid="autonomy-stopped"
                  >
                    <dt className="font-mono min-w-0 truncate">
                      {message(locale, 'autonomy.bound.stopped')}
                    </dt>
                    <dd className="ml-auto flex flex-wrap items-center gap-3 min-w-0">
                      <span className="min-w-0 truncate">
                        {text(dataOf(bounds), 'stop_reason')}
                      </span>
                      {/* The same control the topbar carries, not a second one
                          this screen invented: what stops automation and what
                          this screen bounds are one axis, and resuming it
                          belongs where an operator is already looking at what
                          automation may do. */}
                      <KillSwitchControl
                        viewer={viewer}
                        locale={locale}
                        engaged={stopped}
                      />
                    </dd>
                  </div>
                ) : null}
                {freezes.map((freeze) => (
                  <div
                    key={text(freeze, 'name')}
                    className="flex items-center gap-3"
                    data-testid="bound"
                    data-bound="freeze"
                  >
                    <dt className="font-mono min-w-0 truncate">
                      {text(freeze, 'name')}
                    </dt>
                    <dd className="ml-auto flex items-center gap-2 tabular-nums">
                      {text(freeze, 'start')}–{text(freeze, 'end')}{' '}
                      {text(freeze, 'timezone')}
                    </dd>
                  </div>
                ))}
                {budgets.map((budget) => (
                  <div
                    key={text(budget, 'name')}
                    className="flex items-center gap-3"
                    data-testid="bound"
                    data-bound="budget"
                  >
                    <dt className="font-mono min-w-0 truncate">
                      {text(budget, 'name')}
                    </dt>
                    <dd className="ml-auto flex items-center gap-2 tabular-nums">
                      {formatNumber(locale, number(budget, 'limit'))} /{' '}
                      {text(budget, 'counted_by')}
                    </dd>
                  </div>
                ))}
                {activeOverrides.map((override) => {
                  // Duration and reason in the row itself. An override is a
                  // deliberate, temporary widening of what may happen without a
                  // person, and a list that showed only its name would make
                  // "until when, and who said so" a second lookup nobody makes.
                  return (
                    <div
                      key={override.name}
                      className="flex flex-wrap items-center gap-3"
                      data-testid="bound"
                      data-bound="override"
                    >
                      <dt className="font-mono min-w-0 truncate">{override.name}</dt>
                      <dd className="flex flex-wrap items-center gap-2">
                        <Badge status={override.level} />
                        <span
                          className="text-meta text-muted"
                          data-testid="override-duration"
                        >
                          {message(locale, 'autonomy.override.duration')}{' '}
                          <time
                            dateTime={override.expiresIso}
                            title={override.expiresAbsolute}
                          >
                            {override.expiresRelative}
                          </time>
                        </span>
                        <span
                          className="text-meta text-muted"
                          data-testid="override-reason"
                        >
                          {message(locale, 'autonomy.override.reason')}{' '}
                          {override.reason}
                        </span>
                      </dd>
                    </div>
                  );
                })}
              </dl>
            </Panel>
          ) : null}

          {/* Absent, not disabled, for a viewer who may not write. */}
          {writable && nodeId !== '' ? (
            <Panel
              title={message(locale, 'autonomy.override.panel.title')}
              state={stateOf(bounds, false)}
              dependency={dependencyOf(bounds)}
              labels={panelLabels(
                locale,
                message(locale, 'autonomy.override.panel.title'),
              )}
              empty={{
                heading: message(locale, 'autonomy.empty.heading'),
                body: message(locale, 'autonomy.empty.body'),
                actionLabel: message(locale, 'autonomy.empty.action'),
                href: configurationHref,
              }}
            >
              <OverrideEditor
                nodeId={nodeId}
                levels={OVERRIDE_LEVELS}
                levelLabels={postureLabels(locale, OVERRIDE_LEVELS)}
                active={activeOverrides}
                labels={{
                  grantTitle: message(locale, 'autonomy.override.grant.title'),
                  grantName: message(locale, 'autonomy.override.grant.name'),
                  grantNameHelp: message(locale, 'autonomy.override.grant.nameHelp'),
                  grantLevel: message(locale, 'autonomy.override.grant.level'),
                  grantReason: message(locale, 'autonomy.override.grant.reason'),
                  grantReasonHelp: message(
                    locale,
                    'autonomy.override.grant.reasonHelp',
                  ),
                  grantDuration: message(locale, 'autonomy.override.grant.duration'),
                  grantDurationDefault: message(
                    locale,
                    'autonomy.override.grant.durationDefault',
                  ),
                  grantDurationOneHour: message(
                    locale,
                    'autonomy.override.grant.durationOneHour',
                  ),
                  grantDurationEightHours: message(
                    locale,
                    'autonomy.override.grant.durationEightHours',
                  ),
                  grantDurationTwentyFourHours: message(
                    locale,
                    'autonomy.override.grant.durationTwentyFourHours',
                  ),
                  grantDurationCustom: message(
                    locale,
                    'autonomy.override.grant.durationCustom',
                  ),
                  grantSeconds: message(locale, 'autonomy.override.grant.seconds'),
                  grant: message(locale, 'autonomy.override.grant.submit'),
                  granting: message(locale, 'autonomy.override.grant.granting'),
                  granted: message(locale, 'autonomy.override.grant.granted'),
                  reasonRequired: message(
                    locale,
                    'autonomy.override.grant.reasonRequired',
                  ),
                  revokeTitle: message(locale, 'autonomy.override.revoke.title'),
                  revokeEmpty: message(locale, 'autonomy.override.revoke.empty'),
                  duration: message(locale, 'autonomy.override.duration'),
                  reasonLabel: message(locale, 'autonomy.override.reason'),
                  grantedBy: message(locale, 'autonomy.override.grantedBy'),
                  revoke: message(locale, 'autonomy.override.revoke.submit'),
                  revoking: message(locale, 'autonomy.override.revoke.revoking'),
                  revoked: message(locale, 'autonomy.override.revoke.revoked'),
                  failed: message(locale, 'autonomy.override.failed'),
                  unreachable: message(locale, 'autonomy.override.unreachable'),
                }}
              />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}
