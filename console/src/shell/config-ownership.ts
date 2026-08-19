/**
 * Which Settings page — or which navigable area of the console — an operator
 * edits each configuration field on.
 *
 * The raw configuration editor is being retired, and the only safe way to
 * retire it is to know — as a fact a check can hold, not as an intention —
 * that every field it could reach has somewhere else to be reached. This is
 * that record: one entry per field, in exactly one of three categories.
 *
 * 1. **`CONFIG_FIELD_OWNERS`** — a person edits this field, today, on the
 *    named page. The claim is checked against what each page demonstrably
 *    renders, never against a screen that merely looks related to the group.
 * 2. **`CONFIG_FIELDS_MACHINE`** — the console writes this field about
 *    itself, or the server derives it, and no form is ever offered for it.
 *    Not a gap: a decision that a human choosing this value would be a human
 *    choosing a value nothing reads.
 * 3. **`CONFIG_FIELDS_NO_CONTROL`** — nobody can edit this field anywhere in
 *    the console yet, but it is not a "resto": every entry still names the
 *    page that is, or will be, responsible for it. Two different reasons
 *    live in this one list, and the contract test tells them apart by the
 *    field's own declared type rather than by a tag written here, so the
 *    list cannot drift out of sync with the schema that decides which
 *    reason applies:
 *      - a field the raw editor **cannot reach either** — an object, or an
 *        array the schema describes no entry shape for. Retiring the editor
 *        costs this console nothing it had. This half is permanent; it
 *        shrinks only if a future feature builds an editor for one, which
 *        this migration does not. Eleven fields.
 *      - a field the raw editor **can** reach, with no screen of its own yet.
 *        This half is the real burndown, and it is what keeps the parity
 *        check red until the page named beside it grows a control.
 *
 * **A field appears in exactly one of the three lists.** A field in none of
 * them is a field the schema gained and nobody noticed, and the contract
 * test that reads all three against the schema fails on it by name.
 *
 * **A `page` is checked against every area this console declares** — the
 * nine Settings pages and the rest of the sidebar alike (`agent`,
 * `knowledge`, `integrations`, …) — because ownership is a question of where
 * an operator can navigate, not a question of which part of the shell that
 * happens to be. On `CONFIG_FIELD_OWNERS` a `page` claims a working control
 * exists there today; the same field named on `CONFIG_FIELDS_NO_CONTROL`
 * only claims who is responsible, and claims nothing about what the page
 * renders yet.
 *
 * **What "full parity" turned out to mean.** An earlier reading of this file
 * said the raw editor drew a control only for a string, an integer, a number
 * or a boolean, and concluded that the schema's thirty array and object
 * fields were editable nowhere and cost nothing to drop. That was wrong, and
 * it was wrong in the direction that would have hurt: `preview.tsx`'s
 * `isObjectList` is `type === 'array' && itemFields.length > 0`, and such a
 * field is drawn as an `ObjectList` with add, remove and reorder. Eighteen
 * array fields satisfy it — `transit.destinations`, `surfaces.channels`,
 * `policies.observation.detectors` and the bridge's own lists among them.
 *
 * So the editor reaches a hundred and four fields, not eighty-six, and every
 * one of them has to have somewhere else to be edited before it can be
 * deleted. Fourteen of those eighteen have no human screen at all today,
 * which is exactly the capability regression this record exists to make
 * impossible to miss — and it was nearly missed by the check written to
 * catch it.
 *
 * Ownership is about where a *person* edits a value, not which HTTP route
 * carries the write — several pages here write through their own endpoint
 * rather than the configuration service, and that is an implementation detail
 * of the page, not a different answer to "where do I change this".
 */

export interface ConfigFieldOwner {
  /** The field's path in the configuration schema. */
  readonly path: string;
  /** The `id` of the area or Settings page responsible for it, as `routes.ts` spells it. */
  readonly page: string;
}

/**
 * Every configuration field a person edits today, on the page named beside it.
 *
 * Seeded from what each page demonstrably renders: a page that filters the
 * field list by a path prefix owns every field under it, and one that names
 * individual paths — or writes them through its own endpoint, such as the
 * models editor's per-role save or the single sign-on page's own
 * configure/test/activate flow — owns those. Nothing is claimed here on the
 * strength of a screen looking related to a group — a claim that overstates
 * coverage is worse than no claim, because it is the claim that lets the
 * editor be deleted over a field nobody can reach.
 */
export const CONFIG_FIELD_OWNERS: readonly ConfigFieldOwner[] = [
  // settings-autonomy-guardrails (15) — ten scalars, the four array-shaped
  // fields with a proven endpoint of their own (`rules`, `freezes`,
  // `budgets`, `overrides`), and a fifth array (`custom_patterns`) the
  // generic prefix-scoped editor reaches instead. Those four also have their
  // own purpose-built form (`AutonomyEditor`, `OverrideEditor` on the same
  // page) — but they draw through this same prefixed `ConfigEditor` as an
  // `ObjectList` too, which is a genuine second answer to "where do I change
  // this", not merely a coincidence of the schema. Two more fields on this
  // page — `disabled_rules`, `autonomous_capabilities` — are plain string
  // lists with no control anywhere; they are named on
  // `CONFIG_FIELDS_NO_CONTROL` below, not here.
  { path: 'policies.approvals.expiry_hours', page: 'settings-autonomy-guardrails' },
  { path: 'policies.approvals.threshold', page: 'settings-autonomy-guardrails' },
  {
    path: 'policies.autonomy.allow_unverifiable_actions',
    page: 'settings-autonomy-guardrails',
  },
  { path: 'policies.autonomy.budgets', page: 'settings-autonomy-guardrails' },
  { path: 'policies.autonomy.dry_run', page: 'settings-autonomy-guardrails' },
  { path: 'policies.autonomy.freezes', page: 'settings-autonomy-guardrails' },
  { path: 'policies.autonomy.overrides', page: 'settings-autonomy-guardrails' },
  {
    path: 'policies.autonomy.recurrence_threshold',
    page: 'settings-autonomy-guardrails',
  },
  {
    path: 'policies.autonomy.recurrence_window_seconds',
    page: 'settings-autonomy-guardrails',
  },
  { path: 'policies.autonomy.rules', page: 'settings-autonomy-guardrails' },
  { path: 'policies.guardrails.mode', page: 'settings-autonomy-guardrails' },
  { path: 'policies.guardrails.ruleset', page: 'settings-autonomy-guardrails' },
  { path: 'policies.masking.custom_patterns', page: 'settings-autonomy-guardrails' },
  { path: 'policies.masking.enabled', page: 'settings-autonomy-guardrails' },
  { path: 'policies.masking.level', page: 'settings-autonomy-guardrails' },

  // agent (11) — the four budgets the Topology tab already printed but could
  // not change, the three per-role prompt overrides, the operating-context
  // switch, and the subagent roster, which the advanced section draws with the
  // same list control the raw editor used (`agent.tsx`'s TopologyTab); plus
  // the bridged protocol servers, which the Tools tab's own `capabilities.`
  // advanced section draws the identical way.
  { path: 'agents.max_iterations', page: 'agent' },
  { path: 'agents.max_parallel_subagents', page: 'agent' },
  { path: 'agents.max_subagent_depth', page: 'agent' },
  { path: 'agents.max_subagent_iterations', page: 'agent' },
  { path: 'agents.operating_context.enabled', page: 'agent' },
  { path: 'agents.prompts.diagnose', page: 'agent' },
  { path: 'agents.prompts.intake', page: 'agent' },
  { path: 'agents.prompts.investigator', page: 'agent' },
  { path: 'agents.subagents', page: 'agent' },
  { path: 'agents.tool_budget', page: 'agent' },
  { path: 'capabilities.protocol_servers', page: 'agent' },

  // integrations (1) — the configured-vendor list, drawn by the catalogue's
  // own advanced section as an `ObjectList`, scoped to the `integrations.`
  // prefix. Every other fact about an integration on this page — health,
  // credential, capability, the connect/manage flow — is the read/write half
  // this screen already had; this is the one field that lives in the
  // hierarchical configuration document rather than its own endpoint.
  { path: 'integrations.active', page: 'integrations' },

  // settings-single-sign-on (13) — the eight the provider form walks, the
  // deployment's own on/off switch, and the four claim names the advanced
  // section beneath that same form now exposes.
  { path: 'policies.sso.authorisation_endpoint', page: 'settings-single-sign-on' },
  { path: 'policies.sso.claims.display_name', page: 'settings-single-sign-on' },
  { path: 'policies.sso.claims.email', page: 'settings-single-sign-on' },
  { path: 'policies.sso.claims.groups', page: 'settings-single-sign-on' },
  { path: 'policies.sso.claims.subject', page: 'settings-single-sign-on' },
  { path: 'policies.sso.client_id', page: 'settings-single-sign-on' },
  { path: 'policies.sso.default_node_id', page: 'settings-single-sign-on' },
  { path: 'policies.sso.is_active', page: 'settings-single-sign-on' },
  { path: 'policies.sso.issuer', page: 'settings-single-sign-on' },
  { path: 'policies.sso.jwks_uri', page: 'settings-single-sign-on' },
  { path: 'policies.sso.provider', page: 'settings-single-sign-on' },
  { path: 'policies.sso.redirect_uri', page: 'settings-single-sign-on' },
  { path: 'policies.sso.token_endpoint', page: 'settings-single-sign-on' },

  // settings-schedules-destinations (5) — the routing rules and delivery
  // destinations `transit` declares, and the three delivery surfaces
  // `surfaces` does. Every one is an array the schema describes an entry
  // shape for, so the section draws it with the same list control the raw
  // editor used. `schedules-destinations.tsx`'s advancedDestinationsSection.
  { path: 'surfaces.channels', page: 'settings-schedules-destinations' },
  { path: 'surfaces.notification_sinks', page: 'settings-schedules-destinations' },
  { path: 'surfaces.report_destinations', page: 'settings-schedules-destinations' },
  { path: 'transit.destinations', page: 'settings-schedules-destinations' },
  { path: 'transit.rules', page: 'settings-schedules-destinations' },

  // settings-notifications (6)
  {
    path: 'surfaces.notification_policy.cooldown_seconds',
    page: 'settings-notifications',
  },
  {
    path: 'surfaces.notification_policy.notifications_per_hour',
    page: 'settings-notifications',
  },
  {
    path: 'surfaces.notification_policy.quiet_hours_enabled',
    page: 'settings-notifications',
  },
  {
    path: 'surfaces.notification_policy.quiet_hours_end',
    page: 'settings-notifications',
  },
  {
    path: 'surfaces.notification_policy.quiet_hours_start',
    page: 'settings-notifications',
  },
  { path: 'surfaces.notification_policy.timezone', page: 'settings-notifications' },

  // settings-models-providers (16) — one path pair per role, built the same
  // way `models-editor.tsx`'s own `pathsFor` builds them.
  { path: 'models.diagnose.model', page: 'settings-models-providers' },
  { path: 'models.diagnose.provider', page: 'settings-models-providers' },
  { path: 'models.embedding.model', page: 'settings-models-providers' },
  { path: 'models.embedding.provider', page: 'settings-models-providers' },
  { path: 'models.extraction.model', page: 'settings-models-providers' },
  { path: 'models.extraction.provider', page: 'settings-models-providers' },
  { path: 'models.intake.model', page: 'settings-models-providers' },
  { path: 'models.intake.provider', page: 'settings-models-providers' },
  { path: 'models.investigator.model', page: 'settings-models-providers' },
  { path: 'models.investigator.provider', page: 'settings-models-providers' },
  { path: 'models.selection.model', page: 'settings-models-providers' },
  { path: 'models.selection.provider', page: 'settings-models-providers' },
  { path: 'models.subagent.model', page: 'settings-models-providers' },
  { path: 'models.subagent.provider', page: 'settings-models-providers' },
  { path: 'models.summarisation.model', page: 'settings-models-providers' },
  { path: 'models.summarisation.provider', page: 'settings-models-providers' },

  // knowledge (8) — whether change history, memory, strategy and the
  // knowledge base are consulted, and where change history is read from.
  { path: 'policies.changes.git_host.repository', page: 'knowledge' },
  { path: 'policies.changes.git_host.vendor', page: 'knowledge' },
  { path: 'policies.changes.repository_path', page: 'knowledge' },
  { path: 'policies.knowledge.knowledge_base_enabled', page: 'knowledge' },
  { path: 'policies.knowledge.topology_enabled', page: 'knowledge' },
  { path: 'policies.memory.read_enabled', page: 'knowledge' },
  { path: 'policies.memory.write_enabled', page: 'knowledge' },
  { path: 'policies.strategy.enabled', page: 'knowledge' },

  // settings-alert-intake (28) — what this team watches for, and its own
  // monitoring bridge's scalar settings, plus the bridge's own lists (label
  // rules, log selectors, dashboards, signal precedence) and the detector
  // list. Every one of the six lists draws through this page's same prefixed
  // editor as an `ObjectList` — no purpose-built add/remove/reorder control
  // of its own, and none is needed: the generic one, scoped to this page's
  // prefix, is where a person actually changes it.
  {
    path: 'policies.observation.bridge.dashboard_base_url',
    page: 'settings-alert-intake',
  },
  { path: 'policies.observation.bridge.dashboards', page: 'settings-alert-intake' },
  { path: 'policies.observation.bridge.enabled', page: 'settings-alert-intake' },
  {
    path: 'policies.observation.bridge.history_lookback_seconds',
    page: 'settings-alert-intake',
  },
  { path: 'policies.observation.bridge.label_rules', page: 'settings-alert-intake' },
  { path: 'policies.observation.bridge.log_line_limit', page: 'settings-alert-intake' },
  { path: 'policies.observation.bridge.log_selectors', page: 'settings-alert-intake' },
  {
    path: 'policies.observation.bridge.log_window_seconds',
    page: 'settings-alert-intake',
  },
  { path: 'policies.observation.bridge.logs.enabled', page: 'settings-alert-intake' },
  { path: 'policies.observation.bridge.logs.endpoint', page: 'settings-alert-intake' },
  {
    path: 'policies.observation.bridge.logs.integration',
    page: 'settings-alert-intake',
  },
  { path: 'policies.observation.bridge.logs.name', page: 'settings-alert-intake' },
  {
    path: 'policies.observation.bridge.mapping_interval_seconds',
    page: 'settings-alert-intake',
  },
  {
    path: 'policies.observation.bridge.metrics.enabled',
    page: 'settings-alert-intake',
  },
  {
    path: 'policies.observation.bridge.metrics.endpoint',
    page: 'settings-alert-intake',
  },
  {
    path: 'policies.observation.bridge.metrics.integration',
    page: 'settings-alert-intake',
  },
  { path: 'policies.observation.bridge.metrics.name', page: 'settings-alert-intake' },
  { path: 'policies.observation.bridge.precedence', page: 'settings-alert-intake' },
  {
    path: 'policies.observation.bridge.use_shipped_log_selectors',
    page: 'settings-alert-intake',
  },
  {
    path: 'policies.observation.bridge.use_shipped_rules',
    page: 'settings-alert-intake',
  },
  { path: 'policies.observation.detectors', page: 'settings-alert-intake' },
  {
    path: 'policies.observation.guardian.cluster_shape',
    page: 'settings-alert-intake',
  },
  {
    path: 'policies.observation.guardian.declared_intent_source',
    page: 'settings-alert-intake',
  },
  { path: 'policies.observation.guardian.enabled', page: 'settings-alert-intake' },
  {
    path: 'policies.observation.guardian.heartbeat_destination',
    page: 'settings-alert-intake',
  },
  { path: 'policies.observation.guardian.overrides', page: 'settings-alert-intake' },
  { path: 'policies.observation.pause_reason', page: 'settings-alert-intake' },
  { path: 'policies.observation.paused', page: 'settings-alert-intake' },
];

/**
 * Every configuration field the console writes about itself, or that the
 * server derives — never a value a person types into a form, by decision, so
 * the parity check does not ask either of these fields to appear on a page.
 */
export const CONFIG_FIELDS_MACHINE: readonly string[] = [
  // Written only by the test route (`gateway/http/routes/sso.py`), to the
  // digest of the settings that test ran against. Nobody picks a digest, and
  // editing anything above it clears it back to "" by construction.
  'policies.sso.verified_digest',
  // Written only by the console itself, the moment an operator dismisses the
  // guided tour (`surfaces/first-run/tutorial-setting.ts`'s `TUTORIAL_SETTING`).
  'surfaces.console.tutorial_dismissed',
];

/**
 * Every configuration field with no working control anywhere in the console
 * yet — but never a "resto": each one still names the page responsible for
 * it, real today or the moment somebody builds one.
 *
 * Two different reasons sit in this one list, and the contract test tells
 * them apart from the schema's own declared type rather than from a tag
 * written here — by whether `preview.tsx`'s own `isObjectList` would draw a
 * control for the field, not by whether the JSON type happens to say `array`:
 *
 * - **Genuinely unreachable (11 — 7 arrays with no declared entry shape, 4
 *   free-form objects).** The raw editor never drew a control for either; an
 *   array only gets one when the schema describes what one entry looks like,
 *   and an object only when it is a closed section rather than an
 *   operator-named mapping. These were never editable anywhere, so retiring
 *   the editor changes nothing about them. This half is permanent: it
 *   shrinks only if a future feature chooses to build a mapping editor, which
 *   this migration does not.
 * - **Reachable and not yet built (17).** A scalar, or an array the schema
 *   *does* describe an entry for — which the same prefixed editor already
 *   draws as an `ObjectList`, add/remove/reorder included, the moment a page
 *   scopes itself to that prefix. This half is the real burndown, and it is
 *   what the parity check's authorising invariant reads: while any of these
 *   remain here, the raw editor is not safe to remove. None remain: every
 *   field the editor can reach, list-shaped ones included, now has its
 *   control on the page that owns the subject. That is what makes removing
 *   the editor safe rather than merely intended.
 */
export const CONFIG_FIELDS_NO_CONTROL: readonly ConfigFieldOwner[] = [
  // agent (6) — the capability lists and mappings, and the one operating-
  // context field the schema declares no entry shape for; the advanced
  // section draws every one of these as not editable, correctly — the schema
  // itself never gave the raw editor a control for any of them either.
  { path: 'agents.operating_context.sections', page: 'agent' },
  { path: 'capabilities.disabled', page: 'agent' },
  { path: 'capabilities.disabled_tags', page: 'agent' },
  { path: 'capabilities.enabled', page: 'agent' },
  { path: 'capabilities.parameters', page: 'agent' },
  { path: 'capabilities.protocol_classifications', page: 'agent' },

  // settings-autonomy-guardrails (2) — two plain string lists the schema
  // gives no entry shape to: which named guardrail rules are switched off,
  // and which capabilities may run without an approval. `ConfiguredStrList`
  // is the same type as `capabilities.disabled`, `capabilities.enabled` and
  // `policies.sso.scopes` above and below — a bare list of strings, with
  // nothing inside one entry for any control, generic or bespoke, to draw.
  // Reaching them would mean changing the schema's own shape, or teaching
  // the generic editor to synthesise a one-field entry for every string
  // list it meets; both go well past these two fields.
  {
    path: 'policies.approvals.autonomous_capabilities',
    page: 'settings-autonomy-guardrails',
  },
  { path: 'policies.guardrails.disabled_rules', page: 'settings-autonomy-guardrails' },

  // settings-schedules-destinations (1) — which surfaces a team uses at all
  // is a plain string list the schema describes no entry shape for, so the
  // raw editor never drew a control for it either.
  { path: 'surfaces.enabled', page: 'settings-schedules-destinations' },

  // settings-single-sign-on (2) — the two fields the raw editor's own type
  // rules already excluded from a free-text form: a free-form mapping and a
  // list of strings. The four claim names that used to sit beside them moved
  // to CONFIG_FIELD_OWNERS once the advanced section drew a control for them.
  { path: 'policies.sso.group_to_node', page: 'settings-single-sign-on' },
  { path: 'policies.sso.scopes', page: 'settings-single-sign-on' },
];
