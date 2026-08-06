"""Recording that a rule fired, without recording what it fired on.

The matched value must never be audited for ``redact`` and ``block``. This
module does not record it for ``audit`` either, and the stricter line is
deliberate: the whole point of an ``audit``-action rule is to observe a
shape *before* enforcing it, which means it is pointed at things nobody has yet
decided are safe. Writing those into an append-only table that no retention
sweep may touch is how the audit trail becomes the largest collection of
secrets in the deployment.

What is recorded instead is enough to act on. Which rule, what it would have
done, where it happened, how many times, and whether the operation was refused.
An operator tuning a noisy rule needs the count and the location; they do not
need the value, and if they think they do, the fix is to reproduce it locally
where the local sink gives them the whole line.

The audit write is its own transaction. An operation that was blocked and then
failed must still leave the record of why it was blocked, and sharing a unit of
work with the thing being audited means a rollback takes the record with it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config.constants.security import (
    GUARDRAIL_AUDIT_ACTION,
    GUARDRAIL_AUDIT_RESOURCE_KIND,
)
from platform.guardrails.engine import ScanResult
from platform.guardrails.rules import GuardrailAction
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    PersistenceGateway,
    TenantScope,
)


@dataclass(frozen=True, slots=True)
class GuardrailAuditRecord:
    """One rule firing at one place, described in fields that cannot hold a secret.

    There is no free-form detail field, and that absence is the design. A
    payload that took "whatever the caller passes" is how a matched connection
    string ends up in the audit table one refactor from now.
    """

    org_id: str
    team_id: str
    rule: str
    action: GuardrailAction
    location: str
    match_count: int = 1
    blocked: bool = False
    truncated: bool = False

    def detail(self) -> dict[str, Any]:
        """Return the audit payload: scalars only, and never the matched text."""
        payload: dict[str, Any] = {
            "rule": self.rule,
            "action": self.action.value,
            "location": self.location,
            "matches": self.match_count,
        }
        if self.team_id:
            payload["team_id"] = self.team_id
        if self.truncated:
            payload["truncated"] = True
        return payload

    @property
    def outcome(self) -> AuditOutcome:
        """Return how the audited operation ended."""
        return AuditOutcome.DENIED if self.blocked else AuditOutcome.ALLOWED


class GuardrailAuditor:
    """Writes one append-only event per rule that fired.

    Holds a gateway and opens its own unit of work, so an audit line survives
    the operation it describes.
    """

    __slots__ = ("_clock", "_gateway")

    def __init__(
        self,
        *,
        gateway: PersistenceGateway,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._gateway = gateway
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))

    async def record(self, record: GuardrailAuditRecord) -> AuditEvent:
        """Append ``record`` to the audit trail and return the stored event."""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            occurred_at=self._clock(),
            actor_kind=ActorKind.AGENT,
            actor_id=record.org_id,
            action=GUARDRAIL_AUDIT_ACTION,
            resource_kind=GUARDRAIL_AUDIT_RESOURCE_KIND,
            resource_id=record.rule,
            outcome=record.outcome,
            detail=record.detail(),
        )
        scope = TenantScope(org_id=record.org_id, team_node_id=record.team_id or None)
        async with self._gateway.begin(scope) as unit:
            return await unit.audit.append(event)

    async def record_scan(
        self,
        result: ScanResult,
        *,
        org_id: str,
        team_id: str = "",
        location: str,
    ) -> tuple[AuditEvent, ...]:
        """Append one event per rule that fired in ``result``.

        One per rule rather than one per match. A rule that matched two hundred
        times in one payload is one fact about that rule, and two hundred rows
        would bury it under itself.
        """
        return tuple(
            [
                await self.record(entry)
                for entry in records_for(result, org_id=org_id, team_id=team_id, location=location)
            ]
        )


def records_for(
    result: ScanResult,
    *,
    org_id: str,
    team_id: str = "",
    location: str,
) -> tuple[GuardrailAuditRecord, ...]:
    """Return the records ``result`` produces, one per rule that fired.

    Separated from the auditor so a caller with no database — a unit test, the
    local CLI — can still see exactly what would be written.
    """
    counts: dict[str, int] = {}
    actions: dict[str, GuardrailAction] = {}
    for match in result.matches:
        counts[match.rule] = counts.get(match.rule, 0) + 1
        actions[match.rule] = match.action

    blocking = set(result.blocking_rules)
    return tuple(
        GuardrailAuditRecord(
            org_id=org_id,
            team_id=team_id,
            rule=rule,
            action=actions[rule],
            location=location,
            match_count=count,
            blocked=rule in blocking,
            truncated=result.truncated or result.match_limit_reached,
        )
        for rule, count in counts.items()
    )


def log_fields(result: ScanResult, *, location: str) -> Mapping[str, Any]:
    """Return what a structured log line may say about ``result``.

    Same discipline as the audit payload, and the same reason: a log is read by
    more people than the audit table is, not fewer.
    """
    return {
        "location": location,
        "rules": result.rules_fired,
        "matches": len(result.matches),
        "blocked": result.blocked,
        "truncated": result.truncated or result.match_limit_reached,
    }


__all__ = [
    "GuardrailAuditRecord",
    "GuardrailAuditor",
    "log_fields",
    "records_for",
]
