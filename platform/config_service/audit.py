"""Recording who changed which field, from what to what — with the values filtered.

Every configuration change is audited with actor, timestamp, node, field,
previous value, and new value (FR-021). The last two are the interesting part,
because a configuration audit is the one audit trail that deliberately records
*values*: "somebody changed the masking policy" without saying to what is not a
record anybody can review.

So the values pass through the guardrail engine first (FR-022). A secret-shaped
value is refused at write, but the audit of a *rejected* attempt would otherwise
be the one place the rejected secret survives — written into an append-only
table no retention sweep may touch, which is how an audit trail becomes the
largest collection of credentials in a deployment. Filtering here means the
record of the mistake does not preserve the mistake.

Values are also truncated. A prompt override is thousands of characters, and the
audit table is not where a diff belongs; the row says it truncated rather than
silently shortening.

**One row per field, not one per submission.** "The payments team changed
something" is not reviewable. A row per changed path is what makes an audit
query about a field — "who has ever changed the masking policy" — answerable at
all.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from config.constants.config_service import (
    CONFIG_AUDIT_ACTION_CLEAR,
    CONFIG_AUDIT_ACTION_POLICY,
    CONFIG_AUDIT_ACTION_SET,
    CONFIG_AUDIT_ACTION_TEMPLATE,
    CONFIG_AUDIT_RESOURCE_KIND,
    MAX_AUDITED_VALUE_CHARS,
)
from config.constants.security import REDACTION_PLACEHOLDER
from platform.config_service.field_policy import changed_paths
from platform.config_service.merge import deep_merge
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    PersistenceGateway,
    TenantScope,
)


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ConfigChange:
    """One field, at one node, before and after."""

    node_id: str
    path: str
    before: Any
    after: Any

    @property
    def action(self) -> str:
        """Return whether this change set a value or removed one."""
        return CONFIG_AUDIT_ACTION_CLEAR if self.after is None else CONFIG_AUDIT_ACTION_SET


@dataclass(frozen=True, slots=True)
class ConfigAuditor:
    """Turns a configuration write into audit events, values filtered.

    Holds the engine rather than a ruleset, so a hot reload takes effect on the
    next write without anything having to be rebuilt or told.
    """

    guardrails: GuardrailEngine = field(default_factory=GuardrailEngine)
    clock: Callable[[], datetime] = _utc_now

    def changes(
        self, node_id: str, before: Mapping[str, Any], after: Mapping[str, Any]
    ) -> tuple[ConfigChange, ...]:
        """Return one change per field that differs between ``before`` and ``after``."""
        from platform.config_service import paths

        old = dict(paths.leaves(before))
        new = dict(paths.leaves(after))
        return tuple(
            ConfigChange(node_id=node_id, path=path, before=old.get(path), after=new.get(path))
            for path in changed_paths(before, after)
        )

    def events(
        self,
        changes: Sequence[ConfigChange],
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
        outcome: AuditOutcome = AuditOutcome.ALLOWED,
        action: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        """Return one audit event per change, with both values filtered."""
        at = self.clock()
        return tuple(
            AuditEvent(
                event_id=str(uuid.uuid4()),
                occurred_at=at,
                actor_kind=actor_kind,
                actor_id=actor_id,
                action=action or change.action,
                resource_kind=CONFIG_AUDIT_RESOURCE_KIND,
                resource_id=change.node_id,
                outcome=outcome,
                detail={
                    "field": change.path,
                    "previous_value": self.filtered(change.before),
                    "new_value": self.filtered(change.after),
                },
            )
            for change in changes
        )

    def policy_event(
        self,
        node_id: str,
        path: str,
        summary: Mapping[str, Any],
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
    ) -> AuditEvent:
        """Return the event recording that a field policy was declared or lifted.

        A lock is a change to who may change things, which is a different fact
        from a change to a value and gets its own action so a review can ask for
        one without the other.
        """
        return AuditEvent(
            event_id=str(uuid.uuid4()),
            occurred_at=self.clock(),
            actor_kind=actor_kind,
            actor_id=actor_id,
            action=CONFIG_AUDIT_ACTION_POLICY,
            resource_kind=CONFIG_AUDIT_RESOURCE_KIND,
            resource_id=node_id,
            outcome=AuditOutcome.ALLOWED,
            detail={"field": path, **dict(summary)},
        )

    def template_events(
        self,
        node_id: str,
        template: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
    ) -> tuple[AuditEvent, ...]:
        """Return the events recording a template application (FR-019, FR-021).

        Each changed field is audited as usual, and each row names the template
        it came from — otherwise a review of forty simultaneous changes cannot
        tell a deliberate edit from a bundle somebody applied.
        """
        events = self.events(
            self.changes(node_id, before, after),
            actor_id=actor_id,
            actor_kind=actor_kind,
            action=CONFIG_AUDIT_ACTION_TEMPLATE,
        )
        return tuple(
            AuditEvent(
                event_id=event.event_id,
                occurred_at=event.occurred_at,
                actor_kind=event.actor_kind,
                actor_id=event.actor_id,
                action=event.action,
                resource_kind=event.resource_kind,
                resource_id=event.resource_id,
                outcome=event.outcome,
                detail={**dict(event.detail), "template": template},
            )
            for event in events
        )

    def rejection_events(
        self,
        node_id: str,
        paths_and_reasons: Sequence[tuple[str, str]],
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
    ) -> tuple[AuditEvent, ...]:
        """Return the events recording a refused write, without its values.

        A rejected write is audited because an attempt to store a credential in
        configuration is worth knowing about — and audited *without the value*,
        because it is exactly the value the rejection was keeping out of every
        durable store this deployment has.
        """
        at = self.clock()
        return tuple(
            AuditEvent(
                event_id=str(uuid.uuid4()),
                occurred_at=at,
                actor_kind=actor_kind,
                actor_id=actor_id,
                action=CONFIG_AUDIT_ACTION_SET,
                resource_kind=CONFIG_AUDIT_RESOURCE_KIND,
                resource_id=node_id,
                outcome=AuditOutcome.DENIED,
                detail={"field": path, "reason": reason},
            )
            for path, reason in paths_and_reasons
        )

    def filtered(self, value: Any) -> Any:
        """Return ``value`` as it may be stored: scanned, then bounded.

        Non-strings pass through: a number cannot be a bearer token. A string
        that matches anything is replaced *entirely*, naming the rule rather
        than the text — not merely redacted in place.

        That is stricter than the guardrail engine's own redaction, and
        deliberately. The engine downgrades to observe-only under the ablation
        switch, and an audit row is append-only and exempt from every retention
        sweep. A filtering step that could be turned off by an unrelated switch
        would be the one route by which a rejected credential outlives the
        rejection.
        """
        if isinstance(value, list):
            return [self.filtered(item) for item in value]
        if isinstance(value, Mapping):
            return {key: self.filtered(item) for key, item in value.items()}
        if not isinstance(value, str):
            return value

        result = self.guardrails.scan(value)
        if not result.clean:
            return f"{REDACTION_PLACEHOLDER} [matched {', '.join(result.rules_fired)}]"
        if len(value) <= MAX_AUDITED_VALUE_CHARS:
            return value
        return value[:MAX_AUDITED_VALUE_CHARS] + f"… [truncated, {len(value)} characters]"


async def record(
    gateway: PersistenceGateway, scope: TenantScope, events: Sequence[AuditEvent]
) -> None:
    """Append ``events`` in a transaction of their own.

    Its own transaction deliberately. A write that was refused and then failed
    must still leave the record of why it was refused, and sharing a unit of
    work with the thing being audited means a rollback takes the record with it.
    """
    if not events:
        return
    async with gateway.begin(scope) as uow:
        for event in events:
            await uow.audit.append(event)


def settings_after(before: Mapping[str, Any], patch: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return what a node's settings become when ``patch`` is applied.

    The same ``deep_merge`` the hierarchy uses, so a partial update behaves the
    way an operator expects from every other part of this package.
    """
    return deep_merge(before, patch)


__all__ = ["ConfigAuditor", "ConfigChange", "record", "settings_after"]
