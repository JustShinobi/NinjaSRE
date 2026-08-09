"""Every string a user reads, named once, with English as the source locale.

Not a translation layer — there is one locale and no plan to add a second
tomorrow. What this is, is the scaffolding that makes adding one a catalogue
rather than a rewrite: a string reached by key can be swapped, and a string
written inline at the point it is rendered cannot be found at all.

It earns its place before any translation exists, for two reasons that apply
today. A test can assert that a page says the right thing by naming the key
rather than by repeating the sentence, so rewording a message does not break
twenty tests. And the whole vocabulary of the console is visible in one file,
which is the only way to notice that three screens call the same thing three
different names.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

#: The locale these strings are written in. Article XIII: the source is English
#: whatever language the conversation adding to it is happening in.
SOURCE_LOCALE: Final = "en"


class UnknownMessage(KeyError):
    """A page asked for a string nobody wrote.

    Raised rather than falling back to the key. A page rendering
    ``runs.empty_state`` at a user is a defect, and one that only shows up in
    the screenshot somebody takes during the incident.
    """

    def __init__(self, key: str) -> None:
        super().__init__(
            f"{key!r} is not a message. Add it to MESSAGES rather than writing the "
            f"sentence at the call site, or a translation will never find it."
        )
        self.key = key


#: Every string the console renders, by key. Keys are ``area.thing``, so the
#: whole vocabulary of one screen sorts together.
MESSAGES: Final[Mapping[str, str]] = {
    # -- The shell ------------------------------------------------------------
    "app.name": "NinjaSRE",
    "app.skip_to_content": "Skip to main content",
    "nav.label": "Console sections",
    "nav.runs": "Runs",
    "nav.cost": "Spend",
    "nav.interactions": "Waiting for you",
    "nav.memory": "Memory",
    "nav.knowledge": "Knowledge",
    "nav.config": "Configuration",
    "nav.catalogue": "Catalogue",
    "nav.guardian": "Guardian",
    "nav.admin": "Administration",
    "nav.onboarding": "Set-up",
    "nav.sign_out": "Sign out",
    # -- Identity -------------------------------------------------------------
    "auth.title": "Sign in",
    "auth.heading": "Sign in to NinjaSRE",
    "auth.sso": "Continue with single sign-on",
    "auth.token_label": "API token",
    "auth.token_help": "Paste a token issued for you. It is exchanged for a session and never shown again.",
    "auth.submit": "Sign in",
    "auth.failed": "That token was not accepted. Check it has not been revoked or expired.",
    "auth.expired": "Your session expired. Sign in again to continue.",
    "auth.expiring": "Your session ends soon. Save anything in progress.",
    "auth.impersonating": "You are acting as {principal}. Everything you do is recorded as an impersonation.",
    "auth.impersonation_end": "Stop impersonating",
    # -- Runs -----------------------------------------------------------------
    "runs.title": "Runs",
    "runs.heading": "Investigations",
    "runs.empty": "No investigations yet.",
    "runs.column.run": "Run",
    "runs.column.status": "Status",
    "runs.column.trigger": "Trigger",
    "runs.column.started": "Started",
    "runs.column.duration": "Duration",
    "runs.column.cost": "Cost",
    "runs.column.outcome": "Outcome",
    "runs.column.attention": "Attention",
    "runs.attention_yes": "Waiting for a person",
    "runs.attention_no": "—",
    "runs.filter.legend": "Filter investigations",
    "runs.filter.status": "Status",
    "runs.filter.team": "Team",
    "runs.filter.trigger": "Trigger",
    "runs.filter.since": "Since",
    "runs.filter.attention": "Only those waiting for a person",
    "runs.filter.apply": "Apply filters",
    "runs.start": "Start an investigation",
    "runs.objective_label": "What should be investigated?",
    "runs.live": "This run is live. Events appear as they happen.",
    "runs.replay": "This run has finished. What follows is rebuilt from its recorded events.",
    "runs.cost": "Cost and usage",
    "runs.cost.tokens": "Tokens",
    "runs.cost.total": "Cost",
    "runs.cost.turns": "Turns",
    # -- Spend ----------------------------------------------------------------
    "cost.heading": "Spend",
    "cost.total": "This period",
    "cost.window": "Period",
    "cost.runs": "Runs",
    "cost.tokens": "Tokens",
    "cost.amount": "Cost",
    "cost.all_time": "Every recorded run",
    "cost.since": "Since {date}",
    "cost.until": "Up to {date}",
    "cost.by_team": "By team",
    "cost.by_run": "By run",
    "cost.column.team": "Team",
    "cost.column.run": "Run",
    "cost.column.runs": "Runs",
    "cost.column.tokens": "Tokens",
    "cost.column.cost": "Cost",
    "cost.column.completeness": "Priced",
    "cost.complete": "Complete",
    "cost.floor": "Floor",
    "cost.floor_warning": "{runs} run(s) used a model with no published price. This total is a floor, not a bill.",
    "cost.empty": "Nothing was spent in this period.",
    "runs.add_context": "Add context to this run",
    "runs.context_label": "What else should it know?",
    "runs.cancel": "Cancel this run",
    "runs.take_over": "Take over",
    "runs.reconnected": "The connection dropped and was resumed. No events were lost.",
    "runs.schedules": "Recurring investigations",
    "runs.schedule_empty": "Nothing is scheduled.",
    "runs.schedule_objective": "What should it investigate?",
    "runs.schedule_cron": "How often (cron)",
    "runs.schedule_add": "Schedule this",
    "runs.schedule_next": "Next run",
    # -- Interactions ---------------------------------------------------------
    "interactions.title": "Waiting for you",
    "interactions.heading": "Questions and approvals",
    "interactions.empty": "Nothing is waiting for a decision.",
    "interactions.on_run": "Waiting on this run",
    "interactions.question": "Question",
    "interactions.answer_label": "Your answer",
    "interactions.answer": "Send answer",
    "interactions.approval": "Approval",
    "interactions.target": "Target",
    "interactions.current_state": "Current state",
    "interactions.proposed": "Proposed change",
    "interactions.blast_radius": "Blast radius",
    "interactions.rollback": "Rollback plan",
    "interactions.no_rollback": "No rollback plan is stored for this change.",
    "interactions.evidence": "Evidence behind this",
    "interactions.approve": "Approve",
    "interactions.reject": "Reject",
    "interactions.reject_reason": "Why are you rejecting this?",
    "interactions.closed_elsewhere": "This was decided elsewhere and is no longer waiting.",
    "interactions.rollback_action": "Roll this back",
    "interactions.rollback_window": "Rollback is available until {until}.",
    # -- Memory and knowledge --------------------------------------------------
    "memory.title": "Memory",
    "memory.heading": "What has been learned",
    "memory.search_label": "Component",
    "memory.search": "Search episodes",
    "memory.empty": "No episodes recorded yet.",
    "memory.effectiveness": "Effectiveness",
    "memory.components": "Components",
    "memory.capabilities": "Capabilities used",
    "memory.resolution": "Resolution",
    "memory.from_run": "From run",
    "memory.strategies": "Strategies",
    "memory.strategy_sources": "Built from these episodes",
    "memory.strategy_edit": "Edit this strategy",
    "memory.strategy_edited": "Edited by a person. Edits are preserved when this is regenerated.",
    "memory.topology": "Topology",
    "memory.topology_label": "Service",
    "memory.dependencies": "Depends on",
    "memory.dependents": "Depended on by",
    "memory.blast_radius": "An outage here would reach",
    "memory.topology_unavailable": "Topology is not available in this deployment.",
    "knowledge.title": "Knowledge",
    "knowledge.heading": "Documents",
    "knowledge.empty": "No documents have been ingested.",
    "knowledge.proposals": "Proposals awaiting review",
    "knowledge.proposal_from": "Proposed during",
    "knowledge.approve": "Accept this proposal",
    "knowledge.reject": "Reject this proposal",
    # -- Configuration ---------------------------------------------------------
    "config.title": "Configuration",
    "config.heading": "Organisation",
    "config.tree_label": "Organisation tree",
    "config.node": "Node",
    "config.editor": "Settings for {node}",
    "config.preview": "Preview the effect",
    "config.preview_heading": "What this would change",
    "config.provenance": "Set at",
    "config.provenance_default": "shipped default",
    "config.unchanged": "This change would alter nothing.",
    "config.locked": "Locked by {node}. Change it there, or ask whoever owns that node.",
    "config.gated": "This change is approval-gated. Saving queues it for review rather than applying it.",
    "config.save": "Save",
    "config.template": "Apply a template",
    "config.template_preview": "What applying this template would change",
    "config.value": "Value",
    "config.path": "Setting",
    "config.before": "Now",
    "config.after": "After",
    # -- Catalogue -------------------------------------------------------------
    "catalogue.title": "Catalogue",
    "catalogue.heading": "Capabilities and integrations",
    "catalogue.available": "Available",
    "catalogue.unavailable": "Unavailable",
    "catalogue.reason": "Why not",
    "catalogue.blocked": "Connecting {integration} would enable {count} more.",
    "catalogue.integrations": "Integrations",
    "catalogue.connect": "Connect",
    "catalogue.credential_note": "Credentials go straight to the vault. This console never receives them.",
    # -- Guardian ---------------------------------------------------------------
    "guardian.title": "Guardian",
    "guardian.heading": "What is being watched, and why those numbers",
    "guardian.topology": "This cluster",
    "guardian.enabled": "Watching",
    "guardian.disabled": "Not enabled",
    "guardian.active": "Active detectors",
    "guardian.detector": "Detector",
    "guardian.watches": "Watches",
    "guardian.threshold": "Fires",
    "guardian.rationale": "Why that number",
    "guardian.remedy": "What to do",
    "guardian.severity": "Severity",
    "guardian.signal": "Reading",
    "guardian.origin": "Where the reading comes from",
    "guardian.origin.hypervisor": "Polled from the hypervisor by this deployment",
    "guardian.origin.published": "Queried from your own monitoring; costs the cluster nothing",
    "guardian.none_active": "The shipped detector set is not enabled on this deployment.",
    "guardian.dormant": "Not active on this cluster",
    "guardian.dormant_why": "These need a topology this cluster does not have ({shape}). They are not missing; they are waiting.",
    "guardian.problems": "Overrides that changed nothing",
    # -- Administration ---------------------------------------------------------
    "admin.title": "Administration",
    "admin.heading": "Identity, tokens, and the record",
    "admin.people": "People",
    "admin.grants": "Grants",
    "admin.role": "Role",
    "admin.scope": "Scope",
    "admin.tokens": "Machine tokens",
    "admin.token_name": "Name",
    "admin.token_created": "Created",
    "admin.token_expires": "Expires",
    "admin.token_last_used": "Last used",
    "admin.token_state": "State",
    "admin.token_revoked": "Revoked",
    "admin.token_live": "Live",
    "admin.token_create": "Create a token",
    "admin.token_revoke": "Revoke",
    "admin.token_revoke_all": "Revoke every token for this person",
    "admin.impersonate": "Act as this person",
    "admin.impersonate_note": "Everything you do while impersonating is recorded as an impersonation, and the console says so on every page.",
    "admin.audit": "Audit",
    "admin.audit_export": "Export these events",
    "admin.audit_actor": "Actor",
    "admin.audit_action": "Action",
    "admin.audit_resource": "Resource",
    "admin.audit_outcome": "Outcome",
    "admin.audit_when": "When",
    "admin.policies": "Security policies",
    "admin.sso": "Single sign-on",
    "admin.sso_test": "Test this configuration",
    "admin.sso_activate": "Activate",
    "admin.sso_untested": "Test the configuration before activating it.",
    # -- Onboarding --------------------------------------------------------------
    "onboarding.title": "Set-up",
    "onboarding.heading": "Get this deployment working",
    "onboarding.provider": "Choose a model provider",
    "onboarding.integration": "Connect what it should read",
    "onboarding.team": "Name your first team",
    "onboarding.investigate": "Run your first investigation",
    "onboarding.done": "Done",
    "onboarding.todo": "Not done yet",
    # -- Shared -----------------------------------------------------------------
    "common.none": "—",
    "common.yes": "Yes",
    "common.no": "No",
    "common.unavailable": "The deployment did not answer. Try again in a moment.",
    "common.forbidden": "You do not hold a permission for that.",
    "common.missing": "There is nothing here.",
}


@dataclass(frozen=True, slots=True)
class Catalogue:
    """One locale's strings, and the only way a page gets one."""

    locale: str = SOURCE_LOCALE
    messages: Mapping[str, str] = field(default_factory=lambda: MESSAGES)

    def text(self, key: str, **values: Any) -> str:
        """Return the string ``key`` names, with ``values`` substituted.

        Raises:
            UnknownMessage: nothing is written under that key.
        """
        try:
            template = self.messages[key]
        except KeyError as absent:
            raise UnknownMessage(key) from absent
        return template.format(**values) if values else template

    def has(self, key: str) -> bool:
        """Return whether anything is written under ``key``."""
        return key in self.messages


#: The catalogue every page uses until a second locale exists.
ENGLISH: Final[Catalogue] = Catalogue()


def text(key: str, **values: Any) -> str:
    """Return the English string ``key`` names."""
    return ENGLISH.text(key, **values)


__all__ = [
    "ENGLISH",
    "MESSAGES",
    "SOURCE_LOCALE",
    "Catalogue",
    "UnknownMessage",
    "text",
]
