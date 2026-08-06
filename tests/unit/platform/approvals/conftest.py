"""Shared fixtures for the approval suite.

Everything is a real object except the thing being changed. The gateway is the
in-memory persistence backend, which has real transactions and passes the same
contract suite as PostgreSQL. Only the *applier* is a double, because "what a
configuration write does" is the configuration service's own suite and repeating
it here would make every approval test also a test of the configuration schema.

The applier records what it was asked to apply. That recording is what the
no-bypass assertions are made against: a change that reached the target without
a decision shows up as a call this object made, and no amount of careful reading
of the service proves the same thing.

The helpers are fixtures rather than importable functions on purpose. ``tests/``
is not a package, so a second suite reaching in here by module path would work
only until somebody moved a directory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from platform.approvals.models import ChangeTarget, ChangeType, PendingChange
from platform.approvals.service import ApprovalService
from platform.identity.audit.recorder import AuditContext
from platform.identity.authorisation import PermissionSet
from platform.identity.impersonation import Impersonation
from platform.identity.models import Grant, Principal
from platform.identity.permissions import Role
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ActorKind,
    ConfigNode,
    ConfigNodeKind,
    PersistenceGateway,
    PrincipalKind,
    TenantScope,
)

ORG = "acme"
OTHER_ORG = "globex"

DIVISION = "division-platform"
TEAM = "team-payments"
SQUAD = "squad-checkout"
OTHER_TEAM = "team-search"

REQUESTER = "ada"
REVIEWER = "grace"

#: A fixed instant, so an expiry assertion is arithmetic rather than a race.
EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

#: The four-level chain the blast-radius and routing assertions are stated
#: against, root first.
FOUR_LEVELS: tuple[tuple[str, str | None, ConfigNodeKind], ...] = (
    (ORG, None, ConfigNodeKind.ORGANISATION),
    (DIVISION, ORG, ConfigNodeKind.TEAM),
    (TEAM, DIVISION, ConfigNodeKind.TEAM),
    (SQUAD, TEAM, ConfigNodeKind.SERVICE),
)


class FrozenClock:
    """A clock a test moves on purpose."""

    def __init__(self, at: datetime = EPOCH) -> None:
        self.at = at

    def __call__(self) -> datetime:
        """Return the instant this clock is currently at."""
        return self.at

    def advance(self, **delta: float) -> datetime:
        """Move the clock forward and return the new instant."""
        self.at += timedelta(**delta)
        return self.at


@dataclass(slots=True)
class RecordingApplier:
    """A target that remembers what was applied to it, and what it looks like now.

    ``state`` is what the target reads as. A test assigns to it directly to
    stand for somebody else editing the same thing between the queue and the
    decision, and sets it to ``None`` to stand for the target being deleted —
    the two situations the fingerprint exists to notice.
    """

    state: dict[str, Any] | None = field(default_factory=lambda: {"level": "standard"})
    applied: list[PendingChange] = field(default_factory=list)

    async def read(self, target: ChangeTarget) -> Mapping[str, Any] | None:
        """Return the target's current value, or ``None`` if it is gone."""
        return self.state

    async def apply(self, change: PendingChange) -> None:
        """Apply ``change``'s proposed value to the target."""
        self.applied.append(change)
        self.state = dict(change.proposed)

    @property
    def was_applied(self) -> bool:
        """Return whether anything reached the target at all."""
        return bool(self.applied)


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Yield an in-memory gateway with both organisations and the tree created."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await store_organisation(system, ORG, "Acme Corp")
        await store_organisation(system, OTHER_ORG, "Globex")

    scope = TenantScope(org_id=ORG)
    tree = (*FOUR_LEVELS, (OTHER_TEAM, DIVISION, ConfigNodeKind.TEAM))
    for node_id, parent_id, kind in tree:
        await write_node(store, scope, node_id, parent_id=parent_id, kind=kind)

    yield store
    await store.close()


async def store_organisation(system: Any, org_id: str, name: str) -> None:
    """Create one organisation through the system unit of work."""
    await system.orgs.create_organisation(org_id, name)


async def write_node(
    gateway: PersistenceGateway,
    scope: TenantScope,
    node_id: str,
    *,
    parent_id: str | None,
    kind: ConfigNodeKind,
) -> None:
    """Store one node, carrying its version forward if it already exists.

    Creating an organisation already creates its root, so the root is written
    the same way as everything beneath it rather than being a special case the
    fixture has to remember.
    """
    async with gateway.begin(scope) as uow:
        existing = await uow.config.get(node_id)
        await uow.config.upsert(
            ConfigNode(
                node_id=node_id,
                kind=kind,
                name=node_id,
                parent_id=parent_id,
                values=existing.values if existing is not None else {},
                version=existing.version if existing is not None else 0,
            )
        )


@pytest.fixture
def scope() -> TenantScope:
    """Return the organisation under test."""
    return TenantScope(org_id=ORG)


@pytest.fixture
def clock() -> FrozenClock:
    """Return a clock the test moves."""
    return FrozenClock()


@pytest.fixture
def applier() -> RecordingApplier:
    """Return the target double every change in this suite is applied to."""
    return RecordingApplier()


@pytest.fixture
def service(
    gateway: PersistenceGateway,
    scope: TenantScope,
    applier: RecordingApplier,
    clock: FrozenClock,
) -> ApprovalService:
    """Return a service wired to the recording applier for every change type."""
    return ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        clock=clock,
    )


@pytest.fixture
def target() -> Callable[..., ChangeTarget]:
    """Return a builder for the target a change is queued against."""

    def build(
        identifier: str = TEAM,
        *,
        node_id: str | None = TEAM,
        path: str | None = "policies.masking.level",
    ) -> ChangeTarget:
        return ChangeTarget(identifier=identifier, node_id=node_id, path=path)

    return build


@pytest.fixture
def as_reviewer() -> Callable[..., dict[str, Any]]:
    """Return a builder for the ``decide`` arguments naming who is deciding.

    A builder rather than a value because half the assertions in this suite are
    about *which* principal decided and what they held at the time.
    """

    def build(
        principal_id: str = REVIEWER,
        role: Role = Role.RESPONDER,
        *,
        node_id: str | None = None,
        impersonating: str | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "approver": a_principal(principal_id),
            "permissions": held_by(principal_id, role, node_id=node_id),
        }
        if impersonating is not None:
            arguments["context"] = acting_as(principal_id, impersonating=impersonating)
        return arguments

    return build


@pytest.fixture
def queue_change(
    service: ApprovalService, target: Callable[..., ChangeTarget]
) -> Callable[..., Any]:
    """Return a builder that queues one change and returns it."""

    async def build(
        proposed: Mapping[str, Any] | None = None,
        *,
        change_type: ChangeType = ChangeType.PROMPT,
        requester: str = REQUESTER,
        rationale: str = "the regulator asked for it",
        **target_fields: Any,
    ) -> PendingChange:
        return await service.queue(
            change_type=change_type,
            target=target(**target_fields),
            proposed=dict(proposed) if proposed is not None else {"level": "strict"},
            requester=requester,
            rationale=rationale,
        )

    return build


def a_principal(principal_id: str) -> Principal:
    """Return a human principal in the organisation under test."""
    return Principal(
        principal_id=principal_id,
        org_id=ORG,
        kind=PrincipalKind.USER,
        display_name=principal_id,
    )


def held_by(principal_id: str, role: Role, *, node_id: str | None = None) -> PermissionSet:
    """Return what ``principal_id`` holds, as one grant at ``node_id``."""
    return PermissionSet(
        grants=(
            Grant(
                grant_id=f"{principal_id}-{role.value}",
                principal_id=principal_id,
                role=role,
                node_id=node_id,
            ),
        )
    )


def acting_as(principal_id: str, *, impersonating: str) -> AuditContext:
    """Return the context ``principal_id`` acts under while impersonating somebody.

    The real principal stays on the context, which is the half a self-approval
    check has to read.
    """
    return AuditContext(
        actor_kind=ActorKind.USER,
        actor_id=principal_id,
        impersonation=Impersonation(
            real_principal_id=principal_id,
            node_id=TEAM,
            started_at=EPOCH,
            expires_at=EPOCH + timedelta(minutes=30),
            reason="reproducing the report the team filed",
            subject_principal_id=impersonating,
        ),
    )
