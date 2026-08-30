"""Two write paths, tapped once at the gateway's composition root.

Neither incident state nor a queued decision has a single long-lived object a
composition root can subscribe to the way `platform.runs.stream.RunEventBroker`
does: each request opens its own unit of work, and `.incidents` and
`.approvals` are built fresh from it every time they are read. What *is* built
once, at boot, and handed to everything downstream, is the
`PersistenceGateway` itself — so the tap sits there. `with_deployment_events`
wraps the gateway; every unit of work it opens afterwards hands out an
`.incidents` and an `.approvals` that publish to the deployment channel on
their write paths, and every other property and method passes through
unchanged.

**The decision this stands in for.** The spec's first choice was a live
publisher — `core.agent.interaction.InteractionClosure` or the
`platform.approvals.closure.ClosurePublisher` that wraps it — subscribed once
at the root, the same shape this module uses for incidents. Neither is
constructed anywhere in this deployment's serving path today (only in tests),
so there is no single instance a root composition could subscribe to without
inventing one nobody else uses. Decorating the approval store's own write path
— `create_request`, `decide`, `expire_due` — is the same mechanism this module
already uses for incidents, reachable from the identical root, and it covers
both `/v1/approvals` and `/v1/proposals`, which write through the same store.
What it does not cover: an approval raised as a live in-run interaction never
gets an `interaction_id` on its `decision_*` payload, because nothing
publishes one. That gap is recorded in this feature's control file rather than
patched by registering a subscriber per call site.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from platform.persistence.ports.approval_store import ApprovalRequest, ApprovalState, ApprovalStore
from platform.persistence.ports.incident_store import Incident, IncidentStore
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope, UnitOfWork
from platform.runs.deployment import DeploymentEventBroker, DeploymentEventKind, DeploymentScope


@dataclass(slots=True)
class _EventPublishingIncidentStore:
    """One unit of work's incident store, publishing the writes that open or close one.

    Every other read and write on the port passes straight through — this
    changes nothing about what an incident store answers, only what else
    happens when `upsert` is the write that opened or closed one.
    """

    _inner: IncidentStore
    _events: DeploymentEventBroker

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def upsert(self, incident: Incident) -> Incident:
        """Store ``incident``, and publish `incident_opened`/`incident_closed` when it is one.

        Decided by comparing what was stored under this id before the write to
        what is stored after: a transition among open states (a suppression, a
        correlation) publishes nothing, because FR-007 names only the two
        writes at either end of an incident's life.
        """
        before = await self._inner.get(incident.incident_id)
        stored = await self._inner.upsert(incident)
        if before is None:
            await self._events.publish(
                scope=DeploymentScope.INCIDENT,
                kind=DeploymentEventKind.INCIDENT_OPENED,
                payload={"incident_id": stored.incident_id},
            )
        elif not before.is_closed and stored.is_closed:
            await self._events.publish(
                scope=DeploymentScope.INCIDENT,
                kind=DeploymentEventKind.INCIDENT_CLOSED,
                payload={"incident_id": stored.incident_id},
            )
        return stored


@dataclass(slots=True)
class _EventPublishingApprovalStore:
    """One unit of work's approval store, publishing a proposal's proposed/decided/expired writes.

    Backs both `/v1/approvals` and `/v1/proposals`: both read and write this
    same port, so a decision made through either surface publishes here once,
    from the one place both write through.
    """

    _inner: ApprovalStore
    _events: DeploymentEventBroker

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        stored = await self._inner.create_request(request)
        await self._events.publish(
            scope=DeploymentScope.DECISION,
            kind=DeploymentEventKind.DECISION_PROPOSED,
            payload={"proposal_id": stored.approval_id},
        )
        return stored

    async def decide(
        self,
        approval_id: str,
        *,
        state: ApprovalState,
        decided_by: str,
        decided_at: datetime,
        reason: str | None = None,
    ) -> ApprovalRequest:
        stored = await self._inner.decide(
            approval_id, state=state, decided_by=decided_by, decided_at=decided_at, reason=reason
        )
        await self._events.publish(
            scope=DeploymentScope.DECISION,
            kind=DeploymentEventKind.DECISION_DECIDED,
            payload={"proposal_id": stored.approval_id},
        )
        return stored

    async def expire_due(self, now: datetime) -> tuple[ApprovalRequest, ...]:
        expired = await self._inner.expire_due(now)
        for request in expired:
            await self._events.publish(
                scope=DeploymentScope.DECISION,
                kind=DeploymentEventKind.DECISION_EXPIRED,
                payload={"proposal_id": request.approval_id},
            )
        return expired


@dataclass(slots=True)
class _EventPublishingUnitOfWork:
    """One request's unit of work, with `.incidents` and `.approvals` tapped.

    Every other port — `run_traces`, `config`, `identity`, and the rest — is
    exactly what the wrapped unit of work already returns: this changes two of
    eighteen properties and forwards everything else, including
    `mark_rollback_only`, unmodified.
    """

    _inner: UnitOfWork
    _events: DeploymentEventBroker

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def incidents(self) -> IncidentStore:
        return _EventPublishingIncidentStore(self._inner.incidents, self._events)

    @property
    def approvals(self) -> ApprovalStore:
        return _EventPublishingApprovalStore(self._inner.approvals, self._events)


@dataclass(slots=True)
class _EventPublishingGateway:
    """One deployment's persistence gateway, with every unit of work it opens tapped.

    The only method this overrides is `begin` — `begin_system`, `health` and
    `close` are exactly the wrapped gateway's own, reached through
    `__getattr__`, because a system unit of work never touches an incident or
    an approval and neither of the other two has anything to publish.
    """

    _inner: PersistenceGateway
    _events: DeploymentEventBroker

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @asynccontextmanager
    async def begin(self, scope: TenantScope) -> AsyncIterator[UnitOfWork]:
        async with self._inner.begin(scope) as uow:
            yield _EventPublishingUnitOfWork(uow, self._events)


def with_deployment_events(
    gateway: PersistenceGateway, events: DeploymentEventBroker
) -> PersistenceGateway:
    """Return ``gateway``, wrapped so its incident and approval writes publish to ``events``.

    The one call this feature's composition root makes — `gateway.http.asgi`,
    once, in `build_deployment` — and the only place `_EventPublishingGateway`
    is ever constructed in production. A test wanting the same behaviour calls
    this directly rather than reaching for the private classes above.
    """
    return _EventPublishingGateway(gateway, events)


__all__ = ["with_deployment_events"]
