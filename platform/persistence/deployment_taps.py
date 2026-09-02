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
— `create_request`, `decide`, `discard`, `expire_due` — is the same mechanism
this module already uses for incidents, reachable from the identical root, and it covers
both `/v1/approvals` and `/v1/proposals`, which write through the same store.
What it does not cover: an approval raised as a live in-run interaction never
gets an `interaction_id` on its `decision_*` payload, because nothing
publishes one. That gap is recorded in this feature's control file rather than
patched by registering a subscriber per call site.

**Nothing is announced before it is true.** A tapped write does not publish;
it *holds* the event on the unit of work that earned it, and
`_EventPublishingGateway.begin` releases the whole batch — in the order the
writes happened — only once the wrapped `begin` block has exited without
raising and without being marked rollback-only. The ordering matters because a
unit is more than one write: `platform.approvals.service` stores a request and
its rollback plan inside one transaction, and a failure in the second undoes
the first. Publishing from inside the write would put `decision_proposed` on
the wire for a proposal every reader then fails to find — a console row that
appears, refuses to open, and never goes away.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from platform.persistence.ports.approval_store import ApprovalRequest, ApprovalState, ApprovalStore
from platform.persistence.ports.incident_store import Incident, IncidentStore
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope, UnitOfWork
from platform.runs.deployment import DeploymentEventBroker, DeploymentEventKind, DeploymentScope


@dataclass(frozen=True, slots=True)
class _PendingEvent:
    """One fact a write has established but the transaction has not yet kept."""

    scope: DeploymentScope
    kind: DeploymentEventKind
    payload: Mapping[str, Any]


@dataclass(slots=True)
class _PendingEvents:
    """What one unit of work will announce if — and only if — it commits.

    Handed to the store wrappers in place of the broker itself, which is what
    makes publishing early impossible rather than merely discouraged: a
    wrapper has nothing to publish *to*, and the one object that does hold the
    broker is the gateway, which only reaches it after the unit has ended.

    Carries the organisation the unit was opened for, so every event it
    releases is stamped with the tenant that earned it. Read from the scope
    the caller passed to `begin`, never from anything a request body named.
    """

    org_id: str
    _events: list[_PendingEvent] = field(default_factory=list, repr=False)

    def add(
        self, *, scope: DeploymentScope, kind: DeploymentEventKind, payload: Mapping[str, Any]
    ) -> None:
        """Remember one event to publish when this unit commits."""
        self._events.append(_PendingEvent(scope=scope, kind=kind, payload=payload))

    async def flush(self, events: DeploymentEventBroker) -> None:
        """Publish everything held, oldest first, and forget it."""
        held = tuple(self._events)
        self._events.clear()
        for pending in held:
            await events.publish(
                scope=pending.scope,
                kind=pending.kind,
                payload=pending.payload,
                org_id=self.org_id,
            )


@dataclass(slots=True)
class _EventPublishingIncidentStore:
    """One unit of work's incident store, publishing the writes that open or close one.

    Every other read and write on the port passes straight through — this
    changes nothing about what an incident store answers, only what else
    happens when `upsert` is the write that opened or closed one.
    """

    _inner: IncidentStore
    _pending: _PendingEvents

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def upsert(self, incident: Incident) -> Incident:
        """Store ``incident``, and queue `incident_opened`/`incident_closed` when it is one.

        Decided by comparing what was stored under this id before the write to
        what is stored after: a transition among open states (a suppression, a
        correlation) publishes nothing, because FR-007 names only the two
        writes at either end of an incident's life.
        """
        before = await self._inner.get(incident.incident_id)
        stored = await self._inner.upsert(incident)
        if before is None:
            self._pending.add(
                scope=DeploymentScope.INCIDENT,
                kind=DeploymentEventKind.INCIDENT_OPENED,
                payload={"incident_id": stored.incident_id},
            )
        elif not before.is_closed and stored.is_closed:
            self._pending.add(
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
    _pending: _PendingEvents

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        stored = await self._inner.create_request(request)
        self._pending.add(
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
        self._pending.add(
            scope=DeploymentScope.DECISION,
            kind=DeploymentEventKind.DECISION_DECIDED,
            payload={"proposal_id": stored.approval_id},
        )
        return stored

    async def discard(
        self,
        approval_id: str,
        *,
        discarded_by: str,
        discarded_at: datetime,
    ) -> ApprovalRequest:
        """Discard ``approval_id``, and queue `decision_discarded`.

        A write path of its own: `/v1/proposals/{id}/discard` moves a pending
        or expired request straight to DISCARDED without going through
        `decide`, so the override that covers deciding never saw it. Left
        untapped, discarding was the one change to the queue this channel did
        not carry — and because the console suspends its polling fallback
        while the stream is connected, every client except the one that
        performed it went on showing and counting the row indefinitely.
        """
        stored = await self._inner.discard(
            approval_id, discarded_by=discarded_by, discarded_at=discarded_at
        )
        self._pending.add(
            scope=DeploymentScope.DECISION,
            kind=DeploymentEventKind.DECISION_DISCARDED,
            payload={"proposal_id": stored.approval_id},
        )
        return stored

    async def expire_due(self, now: datetime) -> tuple[ApprovalRequest, ...]:
        expired = await self._inner.expire_due(now)
        for request in expired:
            self._pending.add(
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
    nineteen properties and forwards everything else unmodified.

    `mark_rollback_only` is among the forwarded ones, and forwarding it is now
    load-bearing rather than incidental: the wrapped unit is the one authority
    on whether this transaction is going to keep its writes, and
    `_EventPublishingGateway.begin` asks it — through `is_rollback_only`,
    forwarded the same way — before releasing anything the writes queued.

    Both tapped ports are rebuilt on every read, as the wrapped unit's own
    are, but they share this unit's single `_PendingEvents`: two reads of
    `.approvals` in one request are two wrappers appending to one list, in the
    order the writes actually happened.
    """

    _inner: UnitOfWork
    _pending: _PendingEvents

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def incidents(self) -> IncidentStore:
        return _EventPublishingIncidentStore(self._inner.incidents, self._pending)

    @property
    def approvals(self) -> ApprovalStore:
        return _EventPublishingApprovalStore(self._inner.approvals, self._pending)


@dataclass(slots=True)
class _EventPublishingGateway:
    """One deployment's persistence gateway, with every unit of work it opens tapped.

    The only method this overrides is `begin` — `begin_system`, `health` and
    `close` are exactly the wrapped gateway's own, reached through
    `__getattr__`, because a system unit of work never touches an incident or
    an approval and neither of the other two has anything to publish.

    `begin` is also where the channel's ordering guarantee is kept: it is the
    one place that holds both the broker and the knowledge that a transaction
    has ended, which is why the flush lives here rather than in the stores
    that queued the events.
    """

    _inner: PersistenceGateway
    _events: DeploymentEventBroker

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @asynccontextmanager
    async def begin(self, scope: TenantScope) -> AsyncIterator[UnitOfWork]:
        """Open a tapped unit of work, and publish what it wrote once it commits.

        Three outcomes, one rule — an event is published only for a write the
        database kept:

        * the block raises: the exception propagates out of the wrapped
          ``begin``, which rolls back, and the assignment below never runs;
        * the block marks itself rollback-only: it ends normally, the wrapped
          gateway discards the writes, and the flush is skipped;
        * the block ends normally: the wrapped ``begin`` commits as it exits,
          and only then does the batch reach the broker.

        ``is_rollback_only`` is read inside the wrapped block, on the last
        line where the unit is still open — a unit that has been committed or
        discarded is no longer a thing to ask.
        """
        pending = _PendingEvents(org_id=scope.org_id)
        committed = False
        async with self._inner.begin(scope) as uow:
            yield _EventPublishingUnitOfWork(uow, pending)
            committed = not uow.is_rollback_only
        if committed:
            await pending.flush(self._events)


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
