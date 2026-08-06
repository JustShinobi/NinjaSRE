"""Sandbox lifecycle and refused egress, recorded where nothing can edit them.

Sandbox lifecycle events belong in the run trace, and every blocked egress
attempt is audited with its target, capability, and investigation. Both land here,
in one event type, for a reason worth stating: "a sandbox was provisioned" and
"a sandbox tried to reach an undeclared host" are read together or not at all.
The second is only interpretable against the first — which instance, whose
investigation, under what allow-list.

**The durable sink is the audit repository, not the trace's evidence table.**
Evidence is what the system observed about the incident and is citable in a
conclusion; a provisioning event is neither. The audit trail is append-only by
port design — it has no update and no delete — which is the property a record of
what the isolation layer did actually needs. Correlation back to the run is by
``investigation_id``, which every event carries.

``CollectingSandboxEvents`` is the other implementation, and it is not a test
double: health reporting reads provisioning latencies from it, and a deployment
that has not yet opened a transaction still needs somewhere for a boot-time
event to go.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.security import (
    SANDBOX_AUDIT_RESOURCE_KIND,
    SANDBOX_EGRESS_AUDIT_ACTION,
    SANDBOX_LIFECYCLE_AUDIT_ACTION,
)
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    PersistenceGateway,
    TenantScope,
)
from platform.sandbox.spec import LimitKind, SandboxProfile


class SandboxEventKind(StrEnum):
    """What happened to a sandbox.

    Closed, and each member is something an operator would ask about by name:
    why is provisioning slow (``PROVISIONED``), what killed my capability
    (``LIMIT_EXCEEDED``), why did the vendor call fail (``EGRESS_DENIED``), why
    is this pod still here (``EXPIRED``, ``REAPED``).
    """

    PROVISIONED = "provisioned"
    CLAIMED = "claimed"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_FINISHED = "execution_finished"
    LIMIT_EXCEEDED = "limit_exceeded"
    EGRESS_DENIED = "egress_denied"
    INTERRUPTED = "interrupted"
    TTL_REFRESHED = "ttl_refreshed"
    EXPIRED = "expired"
    RELEASED = "released"
    REAPED = "reaped"
    PROVISIONING_FAILED = "provisioning_failed"

    @property
    def outcome(self) -> AuditOutcome:
        """Return how this kind reads in the audit trail."""
        if self in (SandboxEventKind.EGRESS_DENIED, SandboxEventKind.LIMIT_EXCEEDED):
            return AuditOutcome.DENIED
        if self is SandboxEventKind.PROVISIONING_FAILED:
            return AuditOutcome.FAILED
        return AuditOutcome.ALLOWED


@dataclass(frozen=True, slots=True)
class SandboxEvent:
    """One thing that happened to one sandbox, in fields that cannot hold a secret.

    Every field is a name, an identifier, a duration, or a host. There is no
    free-form payload, for the same reason the credential proxy's audit record
    has none: a detail field that accepts anything is where a rejected request
    body eventually lands, and a request body is where a credential would be if
    something upstream had gone wrong.
    """

    kind: SandboxEventKind
    sandbox_id: str
    profile: SandboxProfile
    org_id: str
    team_id: str
    investigation_id: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    capability: str = ""
    host: str = ""
    limit: LimitKind | None = None
    duration_seconds: float | None = None
    content_digest: str = ""
    reason: str = ""

    def detail(self) -> dict[str, Any]:
        """Return the audit payload: scalars only."""
        payload: dict[str, Any] = {
            "kind": str(self.kind),
            "profile": str(self.profile),
            "team_id": self.team_id,
            "investigation_id": self.investigation_id,
        }
        for name in ("capability", "host", "content_digest", "reason"):
            value = getattr(self, name)
            if value:
                payload[name] = value
        if self.limit is not None:
            payload["limit"] = str(self.limit)
        if self.duration_seconds is not None:
            payload["duration_seconds"] = round(self.duration_seconds, 6)
        return payload

    def audit_event(self) -> AuditEvent:
        """Return this event in the form the audit repository stores."""
        action = (
            SANDBOX_EGRESS_AUDIT_ACTION
            if self.kind is SandboxEventKind.EGRESS_DENIED
            else SANDBOX_LIFECYCLE_AUDIT_ACTION
        )
        return AuditEvent(
            event_id=str(uuid.uuid4()),
            occurred_at=self.occurred_at,
            actor_kind=ActorKind.AGENT,
            actor_id=self.investigation_id,
            action=action,
            resource_kind=SANDBOX_AUDIT_RESOURCE_KIND,
            resource_id=self.sandbox_id,
            outcome=self.kind.outcome,
            detail=self.detail(),
        )


@runtime_checkable
class SandboxEventSink(Protocol):
    """Where a sandbox's lifecycle events go."""

    async def record(self, event: SandboxEvent) -> None:
        """Store ``event``.

        Never raises for a sink that is merely unavailable. A sandbox that
        refused to run because its audit backend was down would turn an
        observability outage into an incident-response outage, and the event is
        recoverable from the run's own trace.
        """


class CollectingSandboxEvents:
    """Keeps events in memory, queryable by investigation.

    Health reporting reads provisioning durations from here, which is why this
    retains rather than counts: "provisioning took 40ms at the median" is the
    number that tells an operator the warm pool is sized correctly, and it
    cannot be recovered from a counter.
    """

    __slots__ = ("_events", "_limit")

    def __init__(self, *, limit: int = 1_000) -> None:
        self._events: list[SandboxEvent] = []
        self._limit = limit

    async def record(self, event: SandboxEvent) -> None:
        """Store ``event``, dropping the oldest once the window is full."""
        self._events.append(event)
        if len(self._events) > self._limit:
            del self._events[: len(self._events) - self._limit]

    @property
    def events(self) -> tuple[SandboxEvent, ...]:
        """Return everything recorded, oldest first."""
        return tuple(self._events)

    def of_kind(self, kind: SandboxEventKind) -> tuple[SandboxEvent, ...]:
        """Return the recorded events of one kind, oldest first."""
        return tuple(event for event in self._events if event.kind is kind)

    def for_investigation(self, investigation_id: str) -> tuple[SandboxEvent, ...]:
        """Return one investigation's events, oldest first."""
        return tuple(event for event in self._events if event.investigation_id == investigation_id)


class AuditingSandboxEvents:
    """Writes lifecycle events to the tenant's append-only audit trail.

    Each event is its own transaction rather than joining the caller's. A
    refused egress must be recorded whether or not the work that triggered it
    goes on to fail, and sharing a unit of work with the thing being audited
    means a rollback takes the record with it — the same reasoning the
    credential proxy's audit writer uses.
    """

    __slots__ = ("_gateway", "_mirror")

    def __init__(
        self, *, gateway: PersistenceGateway, mirror: CollectingSandboxEvents | None = None
    ) -> None:
        self._gateway = gateway
        self._mirror = mirror

    async def record(self, event: SandboxEvent) -> None:
        """Append ``event`` to the audit trail, and to the in-memory mirror if there is one."""
        if self._mirror is not None:
            await self._mirror.record(event)
        scope = TenantScope(org_id=event.org_id)
        async with self._gateway.begin(scope) as uow:
            await uow.audit.append(event.audit_event())


class NullSandboxEvents:
    """Discards everything. The default when a deployment records nothing yet.

    Explicit rather than an ``Optional[SandboxEventSink]`` threaded through
    every runner: an optional sink is a ``if sink is not None`` at every call
    site, and the one that gets forgotten is the one on the failure path.
    """

    __slots__ = ()

    async def record(self, event: SandboxEvent) -> None:
        """Do nothing with ``event``."""


def latency_percentile(
    events: tuple[SandboxEvent, ...], *, percentile: float, kind: SandboxEventKind
) -> float | None:
    """Return the requested percentile of ``kind``'s durations, or ``None`` if there are none.

    Nearest-rank rather than interpolated. The sample here is tens of events,
    not thousands, and an interpolated p95 over eight measurements reports a
    number that was never observed.

    ``ceil`` rather than ``round`` for the rank. Python rounds halves to even,
    so a p50 over five samples would land on the second rather than the third —
    which is the textbook definition of nearest-rank being quietly wrong on
    exactly the sample sizes this sees.
    """
    durations = sorted(
        event.duration_seconds
        for event in events
        if event.kind is kind and event.duration_seconds is not None
    )
    if not durations:
        return None
    index = max(0, min(len(durations) - 1, math.ceil(percentile * len(durations)) - 1))
    return durations[index]


def event_from(
    kind: SandboxEventKind,
    *,
    sandbox_id: str,
    profile: SandboxProfile,
    scope: Mapping[str, str],
    **extra: Any,
) -> SandboxEvent:
    """Return an event for ``kind``, taking tenancy from ``scope``.

    A small constructor because every runner builds these and each one would
    otherwise repeat the same four scope lookups — which is how one of them ends
    up recording the wrong team.
    """
    return SandboxEvent(
        kind=kind,
        sandbox_id=sandbox_id,
        profile=profile,
        org_id=scope["org_id"],
        team_id=scope["team_id"],
        investigation_id=scope["investigation_id"],
        **extra,
    )


__all__ = [
    "AuditingSandboxEvents",
    "CollectingSandboxEvents",
    "NullSandboxEvents",
    "SandboxEvent",
    "SandboxEventKind",
    "SandboxEventSink",
    "event_from",
    "latency_percentile",
]
