/**
 * Which Settings page an operator edits each configuration field on.
 *
 * The raw configuration editor is being retired, and the only safe way to
 * retire it is to know — as a fact a check can hold, not as an intention —
 * that every field it could reach has somewhere else to be reached. This is
 * that record: one entry per field, naming the page that owns it.
 *
 * **A field appears in exactly one of the two lists.** `CONFIG_FIELD_OWNERS`
 * is what has a human screen; `CONFIG_FIELDS_UNOWNED` is what does not, yet.
 * A field in neither is a field the schema gained and nobody noticed, and the
 * contract test that reads both against the schema fails on it by name. That
 * is the whole mechanism: the gap is a number rather than an opinion, and it
 * can only be closed deliberately.
 *
 * **The unowned list is a burndown, and it only shrinks.** Moving a path out
 * of it is the last step of building the screen that owns it, never the first.
 *
 * **What "full parity" was decided to mean.** The raw editor draws a control
 * only for a string, an integer, a number or a boolean, so the thirty array and
 * object fields below are not editable through it either — they are not
 * editable anywhere, and never have been. Retiring that editor therefore has to
 * clear the eighty-six fields it can reach, and nothing more: no operator loses
 * a place to change a value they had. Giving a list or an object a control is a
 * capability this console has never had, and it belongs to a feature that
 * chooses to build it rather than arriving inside a migration.
 *
 * Ownership is about where a *person* edits a value, not which HTTP route
 * carries the write — several pages here write through their own endpoint
 * rather than the configuration service, and that is an implementation detail
 * of the page, not a different answer to "where do I change this".
 */

export interface ConfigFieldOwner {
  /** The field's path in the configuration schema. */
  readonly path: string;
  /** The `id` of the Settings page that edits it, as `routes.ts` spells it. */
  readonly page: string;
}

/**
 * Every configuration field that has a human screen today.
 *
 * Seeded from what each page demonstrably renders: a page that filters the
 * field list by a path prefix owns every field under it, and one that names
 * individual paths owns those. Nothing is claimed here on the strength of a
 * screen looking related to a group — a claim that overstates coverage is
 * worse than no claim, because it is the claim that lets the editor be
 * deleted over a field nobody can reach.
 */
export const CONFIG_FIELD_OWNERS: readonly ConfigFieldOwner[] = [
  {
    path: 'policies.approvals.autonomous_capabilities',
    page: 'settings-autonomy-guardrails',
  },
  { path: 'policies.approvals.expiry_hours', page: 'settings-autonomy-guardrails' },
  { path: 'policies.approvals.threshold', page: 'settings-autonomy-guardrails' },
  { path: 'policies.guardrails.disabled_rules', page: 'settings-autonomy-guardrails' },
  { path: 'policies.guardrails.mode', page: 'settings-autonomy-guardrails' },
  { path: 'policies.guardrails.ruleset', page: 'settings-autonomy-guardrails' },
  { path: 'policies.masking.custom_patterns', page: 'settings-autonomy-guardrails' },
  { path: 'policies.masking.enabled', page: 'settings-autonomy-guardrails' },
  { path: 'policies.masking.level', page: 'settings-autonomy-guardrails' },
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
];

/**
 * Every configuration field with no human screen yet.
 *
 * A hundred and one of them, which is the honest size of what retiring the
 * raw editor still costs. Two facts about this list are worth carrying:
 *
 * Twenty-six of these are arrays and four are objects, and the raw editor
 * cannot edit those either — it draws a control only for a string, an
 * integer, a number or a boolean. So a third of this list is not "still on the
 * old screen"; it is not editable anywhere in the console at all, and never
 * has been.
 *
 * `policies.observation` alone is twenty-eight of them, the largest group in
 * the schema and the one continuous observation reads.
 */
export const CONFIG_FIELDS_UNOWNED: readonly string[] = [
  'agents.max_iterations',
  'agents.max_parallel_subagents',
  'agents.max_subagent_depth',
  'agents.max_subagent_iterations',
  'agents.operating_context.enabled',
  'agents.operating_context.sections',
  'agents.prompts.diagnose',
  'agents.prompts.intake',
  'agents.prompts.investigator',
  'agents.subagents',
  'agents.tool_budget',
  'capabilities.disabled',
  'capabilities.disabled_tags',
  'capabilities.enabled',
  'capabilities.parameters',
  'capabilities.protocol_classifications',
  'capabilities.protocol_servers',
  'integrations.active',
  'models.diagnose.model',
  'models.diagnose.provider',
  'models.embedding.model',
  'models.embedding.provider',
  'models.extraction.model',
  'models.extraction.provider',
  'models.intake.model',
  'models.intake.provider',
  'models.investigator.model',
  'models.investigator.provider',
  'models.selection.model',
  'models.selection.provider',
  'models.subagent.model',
  'models.subagent.provider',
  'models.summarisation.model',
  'models.summarisation.provider',
  'policies.autonomy.allow_unverifiable_actions',
  'policies.autonomy.budgets',
  'policies.autonomy.dry_run',
  'policies.autonomy.freezes',
  'policies.autonomy.overrides',
  'policies.autonomy.recurrence_threshold',
  'policies.autonomy.recurrence_window_seconds',
  'policies.autonomy.rules',
  'policies.changes.git_host.repository',
  'policies.changes.git_host.vendor',
  'policies.changes.repository_path',
  'policies.knowledge.knowledge_base_enabled',
  'policies.knowledge.topology_enabled',
  'policies.memory.read_enabled',
  'policies.memory.write_enabled',
  'policies.observation.bridge.dashboard_base_url',
  'policies.observation.bridge.dashboards',
  'policies.observation.bridge.enabled',
  'policies.observation.bridge.history_lookback_seconds',
  'policies.observation.bridge.label_rules',
  'policies.observation.bridge.log_line_limit',
  'policies.observation.bridge.log_selectors',
  'policies.observation.bridge.log_window_seconds',
  'policies.observation.bridge.logs.enabled',
  'policies.observation.bridge.logs.endpoint',
  'policies.observation.bridge.logs.integration',
  'policies.observation.bridge.logs.name',
  'policies.observation.bridge.mapping_interval_seconds',
  'policies.observation.bridge.metrics.enabled',
  'policies.observation.bridge.metrics.endpoint',
  'policies.observation.bridge.metrics.integration',
  'policies.observation.bridge.metrics.name',
  'policies.observation.bridge.precedence',
  'policies.observation.bridge.use_shipped_log_selectors',
  'policies.observation.bridge.use_shipped_rules',
  'policies.observation.detectors',
  'policies.observation.guardian.cluster_shape',
  'policies.observation.guardian.declared_intent_source',
  'policies.observation.guardian.enabled',
  'policies.observation.guardian.heartbeat_destination',
  'policies.observation.guardian.overrides',
  'policies.observation.pause_reason',
  'policies.observation.paused',
  'policies.sso.authorisation_endpoint',
  'policies.sso.claims.display_name',
  'policies.sso.claims.email',
  'policies.sso.claims.groups',
  'policies.sso.claims.subject',
  'policies.sso.client_id',
  'policies.sso.default_node_id',
  'policies.sso.group_to_node',
  'policies.sso.is_active',
  'policies.sso.issuer',
  'policies.sso.jwks_uri',
  'policies.sso.provider',
  'policies.sso.redirect_uri',
  'policies.sso.scopes',
  'policies.sso.token_endpoint',
  'policies.sso.verified_digest',
  'policies.strategy.enabled',
  'surfaces.channels',
  'surfaces.console.tutorial_dismissed',
  'surfaces.enabled',
  'surfaces.notification_sinks',
  'surfaces.report_destinations',
  'transit.destinations',
  'transit.rules',
];
