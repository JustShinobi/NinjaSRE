"""Every credential resolution, recorded — and never the credential (FR-019).

The audit trail is what answers the question an incident review actually asks:
which team's credential did this capability use, when, and did it work. That is
five fields and a timestamp, and the value is not one of them.

Two decisions here are worth the sentence they cost.

**A refusal is audited as loudly as a success.** ``DENIED`` is the outcome an
operator most needs to see — a team that has been failing to reach PagerDuty for
a week shows up here and nowhere else — and a trail that recorded only what
worked would be a trail of the least interesting events.

**The detail payload is a fixed set of scalars.** Not "whatever the caller
passes". A free-form detail is how a rejected request body ends up in the audit
table, and a request body is exactly where a credential would be if something
upstream had gone wrong. ``ResolutionRecord`` is the schema, and there is no way
to add a field to it at a call site.

The audit write is its own transaction, not the resolver's. A resolution that
fails must still be recorded, and sharing a unit of work with the thing being
audited means a rollback takes the record with it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config.constants.security import (
    CREDENTIAL_RESOLUTION_AUDIT_ACTION,
    CREDENTIAL_RESOLUTION_AUDIT_RESOURCE_KIND,
)
from platform.credentials.proxy.errors import ProxyErrorReason
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    PersistenceGateway,
    TenantScope,
)


@dataclass(frozen=True, slots=True)
class ResolutionRecord:
    """One resolution, described in fields that cannot hold a secret.

    ``handle`` is the credential's *name*, which is safe everywhere by
    construction — that is what makes handles worth having. ``version`` is what
    lets a review say "the call that failed used version 3, and version 4 landed
    two minutes later", which is the sentence that usually ends the
    investigation.
    """

    org_id: str
    team_id: str
    integration: str
    capability: str
    outcome: AuditOutcome
    handle: str = ""
    version: int | None = None
    reason: ProxyErrorReason | None = None
    host: str = ""
    #: How the endpoint's certificate was verified for this call. Present on
    #: every resolution, because "which anchor was in force when this went out"
    #: is a question nothing else can answer six months later.
    trust_anchor: str = ""
    #: The fingerprint when there is one: the declared set on a call that went
    #: out, and the one actually presented on a refusal. Never certificate
    #: material — a PEM in an audit trail is bulk that proves nothing a
    #: fingerprint does not.
    fingerprint: str = ""

    def detail(self) -> dict[str, Any]:
        """Return the audit payload: scalars only, and never a value."""
        payload: dict[str, Any] = {
            "integration": self.integration,
            "capability": self.capability,
            "team_id": self.team_id,
        }
        if self.handle:
            payload["handle"] = self.handle
        if self.version is not None:
            payload["version"] = self.version
        if self.reason is not None:
            payload["reason"] = str(self.reason)
        if self.host:
            payload["host"] = self.host
        if self.trust_anchor:
            payload["trust_anchor"] = self.trust_anchor
        if self.fingerprint:
            payload["fingerprint"] = self.fingerprint
        return payload


class ResolutionAuditor:
    """Writes one append-only event per resolution.

    Holds a gateway and opens its own unit of work, so an audit line survives
    the failure it describes.
    """

    __slots__ = ("_gateway",)

    def __init__(self, *, gateway: PersistenceGateway) -> None:
        self._gateway = gateway

    async def record(self, record: ResolutionRecord) -> AuditEvent:
        """Append ``record`` to the audit trail and return the stored event."""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            occurred_at=datetime.now(UTC),
            actor_kind=ActorKind.AGENT,
            actor_id=record.org_id,
            action=CREDENTIAL_RESOLUTION_AUDIT_ACTION,
            resource_kind=CREDENTIAL_RESOLUTION_AUDIT_RESOURCE_KIND,
            resource_id=record.integration,
            outcome=record.outcome,
            detail=record.detail(),
        )
        scope = TenantScope(org_id=record.org_id, team_node_id=record.team_id or None)
        async with self._gateway.begin(scope) as uow:
            return await uow.audit.append(event)


__all__ = [
    "ResolutionAuditor",
    "ResolutionRecord",
]
