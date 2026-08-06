"""An audit record cannot be modified or deleted through any path.

Three layers, and this suite asserts the two that hold without a database.

1. **The port has no mutator.** ``AuditRepository`` exposes append and read, and
   every implementation is checked for the same absence — a fake that grew a
   private delete would be a fake the retention suite proves nothing against.
2. **The guard is executable.** ``assert_append_only`` is what a deployment runs
   at startup, so a repository that grows a mutator fails on boot rather than on
   the day somebody reviews the log.
3. **The database refuses it.** The trigger is asserted here by declaration; it
   is exercised against a real PostgreSQL in
   ``tests/contract/persistence/test_audit_immutability.py``, which is where
   this repository is allowed to issue a statement at all.

An audit log an administrator can edit is not evidence. That is the whole
reason the enforcement is duplicated rather than centralised: the application
layer can be refactored, and the trigger is what survives the refactor.
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from config.constants.security import (
    AUDIT_IMMUTABILITY_FUNCTION_NAME,
    AUDIT_IMMUTABILITY_TRIGGER_NAME,
)
from platform.identity.audit.guard import (
    MUTATING_METHOD_PREFIXES,
    AuditMutationPath,
    assert_append_only,
)
from platform.persistence.errors import DuplicateRecord, RetentionExempt
from platform.persistence.fakes import FakePersistence
from platform.persistence.fakes.audit_repository import FakeAuditRepository
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditRepository,
    DataClass,
    RetentionPolicy,
    TenantScope,
)
from platform.persistence.ports.transaction import UnitOfWork
from platform.persistence.postgres.audit_guard import (
    AUDIT_APPEND_ONLY_DDL,
    AUDIT_APPEND_ONLY_DROP_DDL,
)
from platform.persistence.postgres.repositories.audit_repository import PostgresAuditRepository

pytestmark = pytest.mark.security

ORG = "acme"
AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

#: Every implementation of the port, so the guarantee is about the port rather
#: than about whichever one a test happened to reach for.
IMPLEMENTATIONS = (AuditRepository, FakeAuditRepository, PostgresAuditRepository)


def public_methods(subject: type) -> tuple[str, ...]:
    """Return the callable attribute names ``subject`` exposes, private included.

    Private ones deliberately. A ``_delete`` is one refactor away from being
    called, and the point of this check is that there is nothing to call.
    """
    return tuple(
        name for name, _ in inspect.getmembers(subject, callable) if not name.startswith("__")
    )


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda i: i.__name__)
def test_no_audit_repository_exposes_a_way_to_change_a_record(implementation: type) -> None:
    """The port and both backends have append and read, and nothing else."""
    offending = [
        name
        for name in public_methods(implementation)
        if name.lstrip("_").startswith(MUTATING_METHOD_PREFIXES)
    ]
    assert not offending, f"{implementation.__name__} exposes {offending}"


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda i: i.__name__)
def test_the_startup_guard_accepts_every_real_implementation(implementation: type) -> None:
    """The guard a deployment runs at boot passes what ships."""
    assert_append_only(implementation)


def test_the_startup_guard_rejects_a_repository_that_grew_a_mutator() -> None:
    """The positive control: a guard that accepts everything proves nothing."""

    class Regressed(FakeAuditRepository):
        async def delete(self, event_id: str) -> None:
            """The method this whole feature exists to make unwritable."""

    with pytest.raises(AuditMutationPath) as raised:
        assert_append_only(Regressed)

    assert "delete" in str(raised.value)


def test_the_guard_also_catches_a_privately_named_mutator() -> None:
    """A leading underscore is not a security boundary."""

    class Regressed(FakeAuditRepository):
        async def _purge_before(self, cutoff: datetime) -> None:
            """A retention sweep somebody added in a hurry."""

    with pytest.raises(AuditMutationPath):
        assert_append_only(Regressed)


async def test_an_appended_event_cannot_be_replaced_by_appending_it_again() -> None:
    """The only write there is refuses to overwrite, so append is not update."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")

    event = AuditEvent(
        event_id="evt-1",
        occurred_at=AT,
        actor_kind=ActorKind.USER,
        actor_id="ada",
        action="config.set",
        resource_kind="config_node",
        resource_id="payments",
        detail={"field": "policies.masking.level"},
    )
    scope = TenantScope(org_id=ORG)
    async with gateway.begin(scope) as uow:
        await uow.audit.append(event)

    async with gateway.begin(scope) as uow:
        with pytest.raises(DuplicateRecord):
            await uow.audit.append(replace(event, action="config.clear"))

    async with gateway.begin(scope) as uow:
        stored = await uow.audit.get("evt-1")
    assert stored is not None
    assert stored.action == "config.set"


def test_the_unit_of_work_offers_no_audit_deletion() -> None:
    """There is no path from a transaction to removing an audit row."""
    assert not [
        name
        for name in public_methods(UnitOfWork)
        if name.lstrip("_").startswith(("purge", "drop"))
    ]


def test_retention_may_not_be_configured_to_delete_audit_records() -> None:
    """The retention sweep cannot be pointed at the audit class."""
    assert DataClass.AUDIT.is_exempt
    with pytest.raises(RetentionExempt):
        RetentionPolicy(data_class=DataClass.AUDIT, retention_days=30)


def test_the_database_layer_declares_a_trigger_that_refuses_mutation() -> None:
    """The third layer, asserted by declaration.

    Application-level immutability is one ORM call away from being bypassed. The
    trigger is what makes the audit log evidence rather than a log, and it is
    exercised for real under ``make test-postgres``.
    """
    assert AUDIT_IMMUTABILITY_FUNCTION_NAME in AUDIT_APPEND_ONLY_DDL
    assert AUDIT_IMMUTABILITY_TRIGGER_NAME in AUDIT_APPEND_ONLY_DDL
    assert AUDIT_IMMUTABILITY_TRIGGER_NAME in AUDIT_APPEND_ONLY_DROP_DDL
