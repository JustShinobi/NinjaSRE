import type { ReactNode } from 'react';

import { TabLinks } from '@/components';
import { Badge } from '@/components/status';
import { formatNumber } from '@/i18n/format';
import type { MessageKey } from '@/i18n/en';
import { message, type Locale } from '@/i18n/messages';
import { timestamp } from '@/i18n/format';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import { KillSwitchControl } from '@/shell/stop';
import type { SurfaceContext } from '../context';
import { AdvancedConfigSection } from '../advanced-config-section';
import {
  AutonomyEditor,
  type EditableBound,
  type EditableRule,
} from '../autonomy-editor';
import {
  AUTONOMY_TABS,
  AUTONOMY_TAB_FILTERS,
  hrefForTab,
  tabFrom,
  tabLabel,
} from './autonomy-tabs';
import { editableFields } from '../editable';
import { formatSeconds } from '../effective-fields';
import { readSetupState } from '../emptiness';
import { requestedSetupReturn, SetupReturnBanner } from '../first-run/return-banner';
import { panelLabels } from '../labels';
import { OverrideEditor, type ActiveOverride } from '../override-editor';
import { OverridePanel } from '../override-panel';
import { Panel } from '../panel';
import { PostureEditor } from '../posture-editor';
import { ConfigEditor } from '../preview';
import { postureLabels, postureName } from '../postures';
import { GuardrailTable } from './guardrail-table';
// The one resolver both appearances of a guardrail's value read from —
// Posture's read-only summary and this tab's own editable table can no
// longer disagree about what a guardrail's cell says, because there is only
// one place that decides it.
import { GUARDRAIL_FIELDS, guardrailRows } from './guardrail-values';
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
import { EffectiveFieldsTable } from '@/design/resolution-preview';
import { placedTree } from '../tree';
import { readViewState, resolveNode } from '../url-state';

/**
 * The single surface that edits what this deployment may do on its own: the
 * rules, the freeze windows, the spend caps, the overrides, and the
 * guardrails (masking, secret detection, approval) — absorbing the tela
 * Autonomy atual whole, at its Settings address.
 *
 * **The loop this page exists to end.** The screen this replaces sent every
 * empty state to `/configuration` — the raw editor, edited by a different
 * path than this one. Every one of those links now goes to the section of
 * this same page that resolves it: creating the first rule, a freeze, a
 * budget, or an override never leaves this document again.
 *
 * **Three tabs, one question each.** `autonomy-tabs.ts` declares the three
 * addresses (Posture, Rules & windows, Guardrails) and which one owns which
 * configuration field; this screen still makes every read it always did,
 * regardless of which tab is active, and only the JSX below the tab strip is
 * conditional on `tab`.
 */

/** The permission that decides whether any editor is on the page at all. */
const WRITE = 'config.write';

/** The levels the deployment declares, least autonomous first. */
const LEVELS = ['propose_only', 'act_on_low_risk', 'act_and_report', 'act_silently'];

/** The levels an override may raise a scope to. Overrides never grant silence. */
const OVERRIDE_LEVELS = ['propose_only', 'act_on_low_risk', 'act_and_report'];

/**
 * The most autonomous level among currently active overrides, or `null`
 * when none is active — an override only ever raises a scope, so the
 * highest one in force is the ceiling the subtitle has to report, not
 * merely the first one this node's bounds happened to list.
 */
function highestActiveLevel(overrides: readonly ActiveOverride[]): string | null {
  return overrides.reduce<string | null>((highest, override) => {
    if (highest === null) return override.level;
    return LEVELS.indexOf(override.level) > LEVELS.indexOf(highest)
      ? override.level
      : highest;
  }, null);
}

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
 * rule.
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

/** The three schema groups this page's guardrails section absorbs. */
const GUARDRAIL_PREFIXES = [
  'policies.masking.',
  'policies.guardrails.',
  'policies.approvals.',
];

/**
 * The four `policies.autonomy` scalars with no control of their own — the
 * array-shaped siblings (`rules`, `freezes`, `budgets`, `overrides`) already
 * have one, above, through `AutonomyEditor` and `OverrideEditor`.
 */
const AUTONOMY_ADVANCED_PREFIX = 'policies.autonomy.';

const AUTONOMY_ADVANCED_FIELD_LIST: readonly {
  readonly path: string;
  readonly label: MessageKey;
  readonly format?: ((value: unknown, locale: Locale) => string) | undefined;
}[] = [
  {
    path: 'policies.autonomy.allow_unverifiable_actions',
    label: 'settings.autonomy.advanced.field.allowUnverifiableActions',
  },
  {
    path: 'policies.autonomy.dry_run',
    label: 'settings.autonomy.advanced.field.dryRun',
  },
  {
    path: 'policies.autonomy.recurrence_threshold',
    label: 'settings.autonomy.advanced.field.recurrenceThreshold',
  },
  {
    path: 'policies.autonomy.recurrence_window_seconds',
    label: 'settings.autonomy.advanced.field.recurrenceWindowSeconds',
    format: formatSeconds,
  },
];

/** The catalogue key for one scope kind, in the order `SCOPE_ORDER` declares them. */
const SCOPE_LABEL: Readonly<Record<string, MessageKey>> = {
  deployment: 'autonomy.scope.deployment',
  team: 'autonomy.scope.team',
  resource_kind: 'autonomy.scope.resource_kind',
  labels: 'autonomy.scope.labels',
  capability: 'autonomy.scope.capability',
  resource: 'autonomy.scope.resource',
  capability_resource: 'autonomy.scope.capability_resource',
};

export async function AutonomyScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search, now, zone } = context;
  const state = readViewState(search, AUTONOMY_TAB_FILTERS);
  const tab = tabFrom(state.filters.tab ?? '');
  const init = authorised(credential);
  const writable = may(viewer, WRITE);

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

  // Read regardless of `writable`: the guardrail summary table below shows
  // the effective value and its origin to any viewer of this page, and every
  // viewer who can reach it already holds `config.write` (the page's own
  // gate), so this only changes behaviour for a future viewer who does not.
  const guardrailFields =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/config/{node_id}/fields', () =>
          read('/v1/config/{node_id}/fields', { ...init, params: { node_id: nodeId } }),
        );

  const rules = [...list(dataOf(policy), 'rules')].sort(
    (left, right) => specificityOf(left) - specificityOf(right),
  );

  // Posture's own reading: the level of the rule scoped to the whole
  // deployment — not the first rule in resolution order, which may be a
  // narrower scope that happens to sort first. Absent that rule entirely,
  // the deployment has not raised itself above the safe default.
  const deploymentRule = rules.find(
    (rule) => text(field(rule, 'scope'), 'kind') === 'deployment',
  );
  const postureLevel =
    deploymentRule === undefined
      ? (LEVELS[0] ?? 'propose_only')
      : text(deploymentRule, 'level');
  // A level the deployment declares and this screen has no name for
  // still has to be selectable, never silently dropped from the list because
  // it is not one of the four known ones.
  const selectableLevels = LEVELS.includes(postureLevel)
    ? LEVELS
    : [...LEVELS, postureLevel];

  const simulated = flag(dataOf(policy), 'dry_run');
  const stopped = flag(dataOf(bounds), 'stopped');
  const freezes = list(dataOf(bounds), 'freezes');
  const budgets = list(dataOf(bounds), 'budgets');
  const overrides = list(dataOf(bounds), 'overrides');

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
  const showBounds =
    nodeId !== '' &&
    (policy.status === 'error' ||
      bounds.status === 'error' ||
      !(rulesEmpty && boundsEmpty));

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

  const editableFreezes: readonly EditableBound[] = freezes.map((freeze) => ({
    name: text(freeze, 'name'),
    record: freeze as Readonly<Record<string, unknown>>,
  }));
  const editableBudgets: readonly EditableBound[] = budgets.map((budget) => ({
    name: text(budget, 'name'),
    record: budget as Readonly<Record<string, unknown>>,
  }));

  // The loop this page exists to end: every empty state that used to send an
  // operator to the raw editor now points at the section of this same page
  // that creates the thing it was missing. That section only exists on the
  // page for a writer at a resolved node — the same gate the editor itself
  // is behind — so an anchor into it is offered only then; anyone else is
  // sent to the Settings hub, a real place rather than a dangling fragment
  // or the raw editor either way.
  const canCreateHere = writable && nodeId !== '';
  const ruleEditorHref = canCreateHere ? '#new-rule' : '/settings';
  // The bounds panel reads on Posture now (the posture reading it is), but
  // the freeze-creation form it points at still lives inside `AutonomyEditor`
  // on Rules & windows — so, unlike `ruleEditorHref`, this anchor has to name
  // the owning tab rather than merely scroll within the current one.
  const boundsEditorHref = canCreateHere
    ? `${hrefForTab(state, 'rules-windows', nodeId)}#new-freeze`
    : '/settings';
  const overrideEditorHref = canCreateHere ? '#override-grant' : '/settings';

  const guardrailCatalogue = editableFields(dataOf(guardrailFields));
  // The three array-shaped guardrail fields — a list's effective value would
  // be its own JSON dump, not a sentence anybody reads as a guardrail's state
  // — keep the generic editor below; the six scalars `GUARDRAIL_FIELDS` names
  // are edited in this tab's own table instead, so a path never carries two
  // controls at once.
  const guardrailEditable = guardrailCatalogue.filter(
    (entry) =>
      GUARDRAIL_PREFIXES.some((prefix) => entry.path.startsWith(prefix)) &&
      !GUARDRAIL_FIELDS.some((scalar) => scalar.path === entry.path),
  );

  const setup = await readSetupState(credential);
  const page = settingsPageFor('settings-autonomy-guardrails');
  // Every tab shares one subtitle: the node this address resolved to, and
  // the posture in force there right now. Falls back to the page's own
  // static description when no node resolved — there is no posture to
  // report yet, and claiming one would be a fact this render does not have.
  // An active override outranks the saved level: what actually governs right
  // now is the override's, on the record and only until it expires, and
  // reporting the saved level instead would understate what this node may do.
  const overriddenLevel = highestActiveLevel(activeOverrides);
  const subtitle =
    nodeId === ''
      ? message(locale, page.context)
      : overriddenLevel === null
        ? message(locale, 'autonomy.subtitle', {
            node: nodeId,
            posture: postureName(locale, postureLevel),
          })
        : message(locale, 'autonomy.subtitle.override', {
            node: nodeId,
            posture: postureName(locale, overriddenLevel),
          });

  // The rare action: absent from every tab's own body, reachable through one
  // button in the header. Absent, not disabled, for a viewer who may not
  // write — the header carries no trigger at all rather than one that opens
  // onto a form nobody may submit.
  const overridePanel =
    writable && nodeId !== '' ? (
      <OverridePanel
        label={message(locale, 'autonomy.override.temporary.title')}
        closeLabel={message(locale, 'autonomy.override.temporary.close')}
      >
        <p
          data-testid="autonomy-override-note"
          className="text-meta text-muted max-w-prose"
        >
          {message(locale, 'autonomy.glossary.override')}
        </p>
        <Panel
          title={message(locale, 'autonomy.override.panel.title')}
          state={stateOf(bounds, false)}
          dependency={dependencyOf(bounds)}
          labels={panelLabels(locale, message(locale, 'autonomy.override.panel.title'))}
          empty={{
            heading: message(locale, 'autonomy.empty.heading'),
            body: message(locale, 'autonomy.empty.body'),
            actionLabel: message(locale, 'autonomy.cta.grantOverride'),
            href: overrideEditorHref,
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
              grantReasonHelp: message(locale, 'autonomy.override.grant.reasonHelp'),
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
              reasonRequired: message(locale, 'autonomy.override.grant.reasonRequired'),
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
      </OverridePanel>
    ) : undefined;

  return (
    <>
      <SettingsPageHeader
        page={page}
        locale={locale}
        context={subtitle}
        // No crumb for a deployment that resolved to no node: a breadcrumb
        // whose last step is blank reads as a page that lost its subject.
        nested={nodeId === '' ? [] : [{ label: nodeId }]}
        actions={overridePanel}
      />

      <TabLinks
        label={message(locale, 'autonomy.tabs')}
        selected={tab}
        tabs={AUTONOMY_TABS.map((each) => ({
          id: each,
          label: tabLabel(locale, each),
          href: hrefForTab(state, each, nodeId),
        }))}
      />

      <div className="mt-4">
        <SetupReturnBanner
          locale={locale}
          setup={setup}
          requested={requestedSetupReturn(search.get('return'))}
        />

        {tab === 'rules-windows' ? (
          <>
            <div className="min-w-0">
              <Panel
                title={message(locale, 'autonomy.rules.title')}
                state={stateOf(policy, rulesEmpty)}
                dependency={dependencyOf(policy)}
                labels={panelLabels(locale, message(locale, 'autonomy.rules.title'))}
                empty={{
                  heading: message(locale, 'autonomy.empty.heading'),
                  body: message(locale, 'autonomy.empty.body'),
                  actionLabel: message(locale, 'autonomy.cta.createRule'),
                  href: ruleEditorHref,
                }}
              >
                {/* The rules list is the region that scrolls when a node
                    accumulates many of them — bounded on its own, so a
                    heavily-ruled node never grows the tab past its budget. */}
                <div
                  data-testid="rules-scroll"
                  className="w-full max-h-96 overflow-auto"
                >
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
                              {level === 'act_on_low_risk'
                                ? text(rule, 'risk_bound')
                                : '—'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Panel>

              {/* Absent, not disabled, for a viewer who may not write. */}
              {writable && nodeId !== '' ? (
                <div className="mt-5">
                  <Panel
                    title={message(locale, 'autonomy.editor.save')}
                    state={stateOf(policy, false)}
                    dependency={dependencyOf(policy)}
                    labels={panelLabels(
                      locale,
                      message(locale, 'autonomy.editor.save'),
                    )}
                    empty={{
                      heading: message(locale, 'autonomy.empty.heading'),
                      body: message(locale, 'autonomy.empty.body'),
                      actionLabel: message(locale, 'autonomy.cta.createRule'),
                      href: ruleEditorHref,
                    }}
                  >
                    <AutonomyEditor
                      nodeId={nodeId}
                      rules={editable}
                      levels={LEVELS}
                      levelLabels={postureLabels(locale, LEVELS)}
                      scopeKindLabels={Object.fromEntries(
                        SCOPE_ORDER.map((kind) => [
                          kind,
                          message(
                            locale,
                            SCOPE_LABEL[kind] ?? 'autonomy.scope.deployment',
                          ),
                        ]),
                      )}
                      dryRun={simulated}
                      freezes={editableFreezes}
                      budgets={editableBudgets}
                      labels={{
                        level: message(locale, 'autonomy.editor.level'),
                        simulationTitle: message(
                          locale,
                          'autonomy.editor.simulation.title',
                        ),
                        simulationDescription: message(
                          locale,
                          'autonomy.editor.simulation.description',
                        ),
                        preview: message(locale, 'autonomy.editor.preview'),
                        previewing: message(locale, 'autonomy.editor.previewing'),
                        explain: message(locale, 'autonomy.editor.explain'),
                        explaining: message(locale, 'autonomy.editor.explaining'),
                        explainIntro: message(locale, 'autonomy.editor.explainIntro'),
                        explainCapability: message(
                          locale,
                          'autonomy.editor.capability',
                        ),
                        explainResource: message(locale, 'autonomy.editor.resource'),
                        save: message(locale, 'autonomy.editor.save'),
                        saving: message(locale, 'autonomy.editor.saving'),
                        saved: message(locale, 'autonomy.editor.saved'),
                        failed: message(locale, 'autonomy.editor.failed'),
                        unreachable: message(locale, 'autonomy.editor.unreachable'),
                        previewFirst: message(locale, 'autonomy.editor.previewFirst'),
                        considered: message(locale, 'autonomy.editor.considered'),
                        changed: message(locale, 'autonomy.editor.changed'),
                        newlyAutonomous: message(
                          locale,
                          'autonomy.editor.newlyAutonomous',
                        ),
                        nothingChanges: message(
                          locale,
                          'autonomy.editor.nothingChanges',
                        ),
                        dryRunOn: message(locale, 'autonomy.editor.dryRunOn'),
                        dryRunOff: message(locale, 'autonomy.editor.dryRunOff'),
                        dryRunBanner: message(locale, 'autonomy.editor.dryRunBanner'),
                        decision: message(locale, 'autonomy.editor.decision'),
                        winningRule: message(locale, 'autonomy.editor.winningRule'),
                        newRuleTitle: message(locale, 'autonomy.editor.newRule.title'),
                        newRuleScope: message(locale, 'autonomy.editor.newRule.scope'),
                        newRuleLevel: message(locale, 'autonomy.editor.newRule.level'),
                        newRuleTeam: message(locale, 'autonomy.editor.newRule.team'),
                        newRuleResourceKind: message(
                          locale,
                          'autonomy.editor.newRule.resourceKind',
                        ),
                        newRuleResourceId: message(
                          locale,
                          'autonomy.editor.newRule.resourceId',
                        ),
                        newRuleCapability: message(
                          locale,
                          'autonomy.editor.newRule.capability',
                        ),
                        newRuleLabelName: message(
                          locale,
                          'autonomy.editor.newRule.labelName',
                        ),
                        newRuleLabelValue: message(
                          locale,
                          'autonomy.editor.newRule.labelValue',
                        ),
                        addRule: message(locale, 'autonomy.editor.newRule.add'),
                        freezesTitle: message(locale, 'autonomy.freezes.title'),
                        freezeName: message(locale, 'autonomy.freeze.name'),
                        freezeStart: message(locale, 'autonomy.freeze.start'),
                        freezeEnd: message(locale, 'autonomy.freeze.end'),
                        freezeReason: message(locale, 'autonomy.freeze.reason'),
                        addFreeze: message(locale, 'autonomy.freeze.add'),
                        budgetsTitle: message(locale, 'autonomy.budgets.title'),
                        budgetName: message(locale, 'autonomy.budget.name'),
                        budgetLimit: message(locale, 'autonomy.budget.limit'),
                        budgetCountedBy: message(locale, 'autonomy.budget.countedBy'),
                        addBudget: message(locale, 'autonomy.budget.add'),
                      }}
                    />
                  </Panel>
                </div>
              ) : null}

              {/* What "a rule" means, placed where one is created rather
                  than above a read-only table with no control to sit after —
                  the mockup puts an explanatory sentence after the control it
                  explains, never before it. */}
              <div className="flex flex-col gap-1 mt-3">
                <p
                  data-testid="autonomy-rule-note"
                  className="text-meta text-muted max-w-prose"
                >
                  {message(locale, 'autonomy.glossary.rule')}
                </p>
                {rules.length > 0 ? (
                  <p data-testid="autonomy-footer" className="text-meta text-muted">
                    {message(locale, 'autonomy.footer')}
                  </p>
                ) : null}
                {simulated ? (
                  <p data-testid="autonomy-dry-run" className="text-meta text-muted">
                    {message(locale, 'autonomy.dry_run')}
                  </p>
                ) : null}
              </div>

              <div className="mt-5">
                <AdvancedConfigSection
                  title={message(locale, 'settings.autonomy.advanced.title')}
                  prefix={AUTONOMY_ADVANCED_PREFIX}
                  nodeId={nodeId}
                  locale={locale}
                  writable={writable}
                  fields={AUTONOMY_ADVANCED_FIELD_LIST.map(
                    ({ path, label, format }) => ({
                      path,
                      label: message(locale, label),
                      format,
                    }),
                  )}
                  rawFields={dataOf(guardrailFields)}
                />
              </div>
            </div>
          </>
        ) : null}

        {tab === 'guardrails' ? (
          // Guardrails: masking, secret detection and approval — the same
          // document a save here writes, never a second registration.
          <div id="guardrails" className="mt-5 flex flex-col gap-3">
            <h3 className="text-strong">
              {message(locale, 'settings.autonomy.guardrails.title')}
            </h3>
            <ul className="text-meta text-muted list-disc pl-5">
              <li data-testid="guardrail-invariant">
                {message(locale, 'settings.autonomy.guardrails.invariant.secret')}
              </li>
              <li data-testid="guardrail-invariant">
                {message(locale, 'settings.autonomy.guardrails.invariant.approval')}
              </li>
            </ul>
            {nodeId === '' ? null : (
              <GuardrailTable
                rows={guardrailRows(guardrailCatalogue, locale)}
                catalogue={guardrailCatalogue}
                writable={writable}
                nodeId={nodeId}
                labels={{
                  setting: message(locale, 'configuration.column.setting'),
                  value: message(locale, 'configuration.column.value'),
                  origin: message(locale, 'configuration.column.provenance'),
                  edit: message(locale, 'settings.autonomy.guardrails.edit'),
                  cancel: message(locale, 'settings.autonomy.guardrails.cancel'),
                  save: message(locale, 'configuration.editor.save'),
                  saving: message(locale, 'configuration.editor.saving'),
                  saved: message(locale, 'configuration.editor.saved'),
                  failed: message(locale, 'configuration.editor.failed'),
                  unreachable: message(locale, 'configuration.editor.unreachable'),
                }}
              />
            )}
            {/* Absent, not an empty result: a search box for a field list
                with nothing left to offer states something false to every
                reader. The six scalars above already draw the whole of
                what the deployment declared under these three prefixes,
                on the datasets that reach this tab today; the day one more
                guardrail-prefixed field exists with no row of its own, this
                is where it appears. */}
            {writable && nodeId !== '' && guardrailEditable.length > 0 ? (
              <ConfigEditor
                nodeId={nodeId}
                fields={guardrailEditable}
                locale={locale}
                labels={{
                  setting: message(locale, 'configuration.column.setting'),
                  value: message(locale, 'configuration.column.value'),
                  submit: message(locale, 'configuration.editor.submit'),
                  save: message(locale, 'configuration.editor.save'),
                  saving: message(locale, 'configuration.editor.saving'),
                  saved: message(locale, 'configuration.editor.saved'),
                  failed: message(locale, 'configuration.editor.failed'),
                  unreachable: message(locale, 'configuration.editor.unreachable'),
                  before: message(locale, 'configuration.preview.before'),
                  after: message(locale, 'configuration.preview.after'),
                  locked: message(locale, 'configuration.locked'),
                  lockedDetail: message(locale, 'configuration.locked.detail'),
                  gated: message(locale, 'configuration.gated'),
                  gatedDetail: message(locale, 'configuration.gated.detail'),
                  provenance: message(locale, 'configuration.column.provenance'),
                  setAt: message(locale, 'configuration.editor.setAt'),
                  usingDefault: message(locale, 'configuration.editor.usingDefault'),
                  toc: message(locale, 'configuration.editor.toc'),
                  search: message(locale, 'configuration.editor.search'),
                  searchEmpty: message(locale, 'configuration.editor.searchEmpty'),
                  generalSection: message(
                    locale,
                    'configuration.editor.generalSection',
                  ),
                  empty: message(locale, 'configuration.preview.empty.heading'),
                  previewFirst: message(locale, 'configuration.editor.previewFirst'),
                  clear: message(locale, 'configuration.editor.clear'),
                  cleared: message(locale, 'configuration.editor.cleared'),
                  redundant: message(locale, 'configuration.editor.redundant'),
                  reverts: message(locale, 'configuration.editor.reverts'),
                  notEditable: message(locale, 'configuration.editor.notEditable'),
                  inherited: message(locale, 'configuration.editor.inherited'),
                  useSuggested: message(locale, 'configuration.editor.useSuggested'),
                  addEntry: message(locale, 'configuration.editor.addEntry'),
                  removeEntry: message(locale, 'configuration.editor.removeEntry'),
                  moveUp: message(locale, 'configuration.editor.moveUp'),
                  moveDown: message(locale, 'configuration.editor.moveDown'),
                  entryPosition: message(locale, 'configuration.editor.entryPosition'),
                  emptyList: message(locale, 'configuration.editor.emptyList'),
                }}
              />
            ) : null}

            {/* What this group is, placed after the table it describes —
                the mockup puts an explanatory sentence after the control it
                explains, never before it (see the rule note on Rules &
                windows, and the bound/override notes on Posture). */}
            <p
              data-testid="guardrail-note"
              className="text-meta text-muted max-w-prose"
            >
              {message(locale, 'settings.autonomy.guardrails.lead')}
            </p>
          </div>
        ) : null}

        {tab === 'posture' ? (
          <div className="flex flex-col gap-5">
            {/* The decision itself, first — a level and a Save beside it,
                before anything that only reads the posture this produces.
                Absent, not disabled, for a viewer who may not write: the
                subtitle above already states the posture in force for
                anyone who cannot change it. */}
            {writable && nodeId !== '' ? (
              <div data-testid="posture-card" className="flex flex-col gap-3">
                <h4 className="text-strong">
                  {message(locale, 'autonomy.posture.title')}
                </h4>
                <PostureEditor
                  nodeId={nodeId}
                  levels={selectableLevels}
                  levelLabels={postureLabels(locale, selectableLevels)}
                  currentLevel={postureLevel}
                  rules={rules}
                  dryRun={simulated}
                  freezes={editableFreezes}
                  budgets={editableBudgets}
                  riskBound={DEFAULT_RISK_BOUND}
                  labels={{
                    level: message(locale, 'autonomy.editor.level'),
                    save: message(locale, 'autonomy.posture.save'),
                    saving: message(locale, 'autonomy.editor.saving'),
                    saved: message(locale, 'autonomy.editor.saved'),
                    failed: message(locale, 'autonomy.editor.failed'),
                    unreachable: message(locale, 'autonomy.editor.unreachable'),
                  }}
                />
                {/* The absence of a rule is the safe default,
                    named as such, after the control it explains — never
                    before it. */}
                {rulesEmpty ? (
                  <p
                    data-testid="autonomy-posture-empty"
                    className="text-meta text-muted max-w-prose"
                  >
                    {message(locale, 'autonomy.empty.body')}{' '}
                    {message(locale, 'autonomy.posture.empty.scopeLead')}{' '}
                    <a
                      href={hrefForTab(state, 'rules-windows', nodeId)}
                      className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
                    >
                      {tabLabel(locale, 'rules-windows')}
                    </a>
                    .
                  </p>
                ) : null}
              </div>
            ) : null}

            {/* The guardrails summary Posture carries — read
                only, the same resolver the Guardrails tab's own table uses,
                so the two appearances can never disagree. */}
            <div
              data-testid="posture-guardrails-summary"
              className="flex flex-col gap-3"
            >
              <h4 className="text-strong">
                {message(locale, 'autonomy.posture.guardrails.title')}
              </h4>
              {nodeId === '' ? null : (
                <EffectiveFieldsTable
                  rows={guardrailRows(guardrailCatalogue, locale)}
                  labels={{
                    setting: message(locale, 'configuration.column.setting'),
                    value: message(locale, 'configuration.column.value'),
                    origin: message(locale, 'configuration.column.provenance'),
                  }}
                />
              )}
            </div>

            {/* The posture reading: what this deployment may do on its own,
                right now — stopped or not, which freezes and budgets
                currently bound it, and any temporary override raising it.
                Read regardless of `writable`, the same as the guardrail
                summary below it is meant to be once it lands here too. */}
            {showBounds ? (
              <Panel
                title={message(locale, 'autonomy.bounds.title')}
                state={stateOf(bounds, boundsEmpty)}
                dependency={dependencyOf(bounds)}
                labels={panelLabels(locale, message(locale, 'autonomy.bounds.title'))}
                empty={{
                  heading: message(locale, 'autonomy.empty.heading'),
                  body: message(locale, 'autonomy.empty.body'),
                  actionLabel: message(locale, 'autonomy.cta.recordBound'),
                  href: boundsEditorHref,
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
                  {activeOverrides.map((override) => (
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
                  ))}
                </dl>
              </Panel>
            ) : null}

            <p
              data-testid="autonomy-bound-note"
              className="text-meta text-muted max-w-prose"
            >
              {message(locale, 'autonomy.glossary.bound')}
            </p>
          </div>
        ) : null}
      </div>
    </>
  );
}
