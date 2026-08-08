"""Every fake satisfies the port it stands in for, at runtime as well as statically.

``platform/persistence/fakes/gateway.py`` carries a ``TYPE_CHECKING`` block that
makes ``make typecheck`` fail on a signature that drifts. This file is the other
half: a runtime check that the methods are actually there, which catches the case
mypy cannot — a property that raises, an attribute that is only defined under
``TYPE_CHECKING``, a repository the unit of work forgot to expose.

Neither check is sufficient alone. ``runtime_checkable`` compares names and not
signatures; mypy compares signatures and never runs the code.
"""

from __future__ import annotations

import pytest

from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ApprovalStore,
    AuditRepository,
    ConfigRepository,
    CredentialStore,
    EpisodeStore,
    EstateRepository,
    IdentityRepository,
    KnowledgeStore,
    OrgDirectory,
    PersistenceGateway,
    RetentionSweeper,
    RunTraceStore,
    ScheduleStore,
    SessionStore,
    SignalStore,
    TenantScope,
    TokenDirectory,
    TopologyGraph,
    UnitOfWork,
    VectorIndex,
)
from platform.persistence.ports.schedule_store import JobDispatcher
from platform.persistence.ports.transaction import SystemUnitOfWork

pytestmark = pytest.mark.unit

#: The fourteen, as ``(attribute on the unit of work, the protocol it must satisfy)``.
TENANT_PORTS = (
    ("config", ConfigRepository),
    ("identity", IdentityRepository),
    ("audit", AuditRepository),
    ("run_traces", RunTraceStore),
    ("sessions", SessionStore),
    ("episodes", EpisodeStore),
    ("vectors", VectorIndex),
    ("topology", TopologyGraph),
    ("knowledge", KnowledgeStore),
    ("approvals", ApprovalStore),
    ("schedules", ScheduleStore),
    ("credentials", CredentialStore),
    ("estate", EstateRepository),
    ("signals", SignalStore),
)

SYSTEM_PORTS = (
    ("orgs", OrgDirectory),
    ("tokens", TokenDirectory),
    ("jobs", JobDispatcher),
    ("retention", RetentionSweeper),
)


def test_the_specification_names_exactly_fourteen_ports() -> None:
    """A fifteenth is a specification change, not a refactor.

    The count was twelve until the estate arrived and thirteen until the signal
    history did, which is exactly what this test is for: adding a port is a
    deliberate act with a plan behind it, and the number moving without one is
    the thing worth catching.
    """
    assert len(TENANT_PORTS) == 14


def test_the_in_memory_gateway_is_a_persistence_gateway() -> None:
    assert isinstance(FakePersistence(), PersistenceGateway)


@pytest.mark.parametrize(("attribute", "port"), TENANT_PORTS, ids=[n for n, _ in TENANT_PORTS])
async def test_every_tenant_scoped_fake_satisfies_its_port(attribute: str, port: type) -> None:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme Corp")

    async with store.begin(TenantScope(org_id="acme")) as uow:
        assert isinstance(uow, UnitOfWork)
        assert isinstance(getattr(uow, attribute), port)


@pytest.mark.parametrize(("attribute", "port"), SYSTEM_PORTS, ids=[n for n, _ in SYSTEM_PORTS])
async def test_every_system_scoped_fake_satisfies_its_port(attribute: str, port: type) -> None:
    store = FakePersistence()
    async with store.begin_system() as system:
        assert isinstance(system, SystemUnitOfWork)
        assert isinstance(getattr(system, attribute), port)


async def test_a_scope_needs_an_organisation() -> None:
    with pytest.raises(ValueError, match="organisation id"):
        TenantScope(org_id="")


async def test_narrowing_stays_inside_the_same_organisation() -> None:
    # Narrowing is a convenience within a tenant, never a second security
    # boundary. The boundary that matters is the organisation, and it does not
    # move.
    narrowed = TenantScope(org_id="acme").narrowed_to("payments")

    assert narrowed.org_id == "acme"
    assert narrowed.team_node_id == "payments"
