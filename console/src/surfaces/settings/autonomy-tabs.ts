import { message, type Locale } from '@/i18n/messages';
import type { MessageKey } from '@/i18n/en';
import { hrefFor, withFilter, type FilterName, type ViewState } from '../url-state';

/**
 * The three questions Autonomy & guardrails answers, and the two things every
 * one of them needs to get right: which tab an address opens to, and which
 * tab owns a given configuration field.
 *
 * Mirrors the tab-by-address pattern the Decisions and Agent screens already
 * use (`surfaces/screens/decisions.tsx`'s `DECISIONS_TABS`/`tabFrom`,
 * `surfaces/screens/agent.tsx`'s `AGENT_TABS`/`AGENT_FILTERS`) rather than
 * inventing a second mechanism: a tab is a filter alongside the scope node,
 * not a parallel piece of client state, and the tab a viewer lands on is a
 * pure function of the address, never of what happened to render last.
 */

/** Posture first: it is what a viewer lands on with no tab named at all. */
export const AUTONOMY_TABS = ['posture', 'rules-windows', 'guardrails'] as const;

export type AutonomyTab = (typeof AUTONOMY_TABS)[number];

/**
 * The filters this screen's address carries: the scope node, exactly as
 * every other node-scoped screen already declares it, and the tab beside it.
 * Declared together so a screen that reads one through `readViewState` reads
 * both, and a tab switch built through `withFilter`/`hrefFor` never has to
 * choose between keeping the node and keeping the tab.
 */
export const AUTONOMY_TAB_FILTERS: readonly FilterName[] = ['node', 'tab'];

/** The tab the address names, and Posture when it names nothing this product declares. */
export function tabFrom(value: string): AutonomyTab {
  return AUTONOMY_TABS.find((tab) => tab === value) ?? AUTONOMY_TABS[0];
}

/** `tab`'s display name, resolved for `locale` — the exact words the tab strip renders. */
export function tabLabel(locale: Locale, tab: AutonomyTab): string {
  return message(locale, `autonomy.tab.${tab}` as MessageKey);
}

/**
 * The address a tab link points at: `tab`, with the scope node carried
 * forward so switching tabs never drops which node the screen is showing.
 *
 * `nodeId` is the node the screen actually resolved — not read back out of
 * `state.filters.node` — because a first visit to the route names no node in
 * its own address at all (the screen falls back to the viewer's own team, or
 * the tree root) and a tab-switch link built from an address that never
 * named one would carry that same silence forward. Pinning the resolved node
 * explicitly is what keeps every tab pointed at the node a viewer is
 * actually looking at, the same way `agent.tsx`'s own tab-address builder
 * already pins it for its four tabs.
 */
export function hrefForTab(state: ViewState, tab: AutonomyTab, nodeId: string): string {
  const scoped = nodeId === '' ? state : withFilter(state, 'node', nodeId);
  return hrefFor('', withFilter(scoped, 'tab', tab), AUTONOMY_TAB_FILTERS);
}

/** One configuration field, and the single tab that presents it. */
export interface AutonomyTabField {
  readonly path: string;
  readonly tab: AutonomyTab;
}

/**
 * Every configuration field this page owns — the seventeen paths
 * `shell/config-ownership.ts` assigns to `settings-autonomy-guardrails` —
 * claimed by exactly one of the three tabs above.
 *
 * Declared as data, not inferred from where a control happens to sit in
 * JSX: the reorganisation into tabs is exactly the change that loses a field
 * silently, and a map a test can walk field by field is what turns "did we
 * lose one" from a question answered by reading into one answered by
 * running something.
 *
 * The split follows each tab's own question. Rules & windows is "when this
 * deployment cannot act on its own", so it holds every scalar and array
 * under `policies.autonomy.` that governs rule evaluation — the rules
 * themselves, freeze windows, budgets, the simulation switch (`dry_run`),
 * and the two fields that narrow what a rule is allowed to permit
 * (`allow_unverifiable_actions`, the recurrence throttle). Guardrails is
 * "what always holds", so it holds every scalar and array under
 * `policies.guardrails.`, `policies.masking.` and `policies.approvals.` —
 * none of those three groups is conditional on a rule the way autonomy is.
 *
 * `policies.autonomy.overrides` is the one path with no obvious home: the
 * override panel this feature introduces is reachable identically from
 * every tab's own header, so it sits inside no single tab's body at all.
 * It is assigned to Posture — not Rules & windows, where the rest of
 * `policies.autonomy.` lives — because an override is not a rule, a freeze
 * or a budget; it is a temporary elevation of exactly the question Posture
 * answers ("what can this deployment do on its own"), and Posture's own
 * subtitle is where the posture an active override produces is stated. A
 * future Posture control that edits this same node's deployment-scope rule
 * (its own "level, and a Save beside it") will write into the same
 * `policies.autonomy.rules` path this map assigns to Rules & windows — a
 * second surface touching one field, the same shape Posture's read-only
 * guardrail summary already has by design; it is not a second owner of the
 * path, only a second place a slice of it is shown or changed.
 */
export const AUTONOMY_TAB_FIELDS: readonly AutonomyTabField[] = [
  // Posture (1) — the temporary elevation of what this deployment may do alone.
  { path: 'policies.autonomy.overrides', tab: 'posture' },

  // Rules & windows (7) — when the deployment may not act alone: the rules
  // themselves, the windows and caps that override any rule's decision, the
  // simulation switch, and the two fields that narrow what a rule may permit.
  { path: 'policies.autonomy.allow_unverifiable_actions', tab: 'rules-windows' },
  { path: 'policies.autonomy.budgets', tab: 'rules-windows' },
  { path: 'policies.autonomy.dry_run', tab: 'rules-windows' },
  { path: 'policies.autonomy.freezes', tab: 'rules-windows' },
  { path: 'policies.autonomy.recurrence_threshold', tab: 'rules-windows' },
  { path: 'policies.autonomy.recurrence_window_seconds', tab: 'rules-windows' },
  { path: 'policies.autonomy.rules', tab: 'rules-windows' },

  // Guardrails (9) — what always holds, whatever a rule decides: masking,
  // secret detection, and the approval gate.
  { path: 'policies.approvals.autonomous_capabilities', tab: 'guardrails' },
  { path: 'policies.approvals.expiry_hours', tab: 'guardrails' },
  { path: 'policies.approvals.threshold', tab: 'guardrails' },
  { path: 'policies.guardrails.disabled_rules', tab: 'guardrails' },
  { path: 'policies.guardrails.mode', tab: 'guardrails' },
  { path: 'policies.guardrails.ruleset', tab: 'guardrails' },
  { path: 'policies.masking.custom_patterns', tab: 'guardrails' },
  { path: 'policies.masking.enabled', tab: 'guardrails' },
  { path: 'policies.masking.level', tab: 'guardrails' },
];

/** The tab that owns `path`, or `undefined` when this map assigns nobody — a
 * detectable, nameable gap rather than a silent default to Posture. */
export function tabOwning(path: string): AutonomyTab | undefined {
  return AUTONOMY_TAB_FIELDS.find((entry) => entry.path === path)?.tab;
}
