"""Immutability, the half that needs a real database: the trigger refuses mutation.

``tests/security/test_audit_immutability.py`` asserts that no code path exposes
a way to change an audit record. This file asserts the layer beneath that: even
with a connection and a statement of your own, the database says no.

It lives here because this is the one test tree allowed to issue SQL, and it is
skipped without PostgreSQL — the fakes have no trigger to exercise, and a
version of this assertion that passed against them would be asserting nothing.
Run it with ``make test-postgres``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import PRIMARY_ORG
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    PersistenceGateway,
    TenantScope,
)

pytestmark = pytest.mark.contract

AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
EVENT_ID = "evt-immutable"


async def _seed_event(gateway: PersistenceGateway) -> None:
    """Append the record the statements below try, and fail, to remove."""
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        await uow.audit.append(
            AuditEvent(
                event_id=EVENT_ID,
                occurred_at=AT,
                actor_kind=ActorKind.USER,
                actor_id="ada",
                action="config.set",
                resource_kind="config_node",
                resource_id="payments",
                detail={"field": "policies.masking.level"},
            )
        )


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param("UPDATE audit_events SET actor_id = 'somebody-else'", id="update"),
        pytest.param("DELETE FROM audit_events", id="delete"),
        pytest.param("TRUNCATE TABLE audit_events", id="truncate"),
    ],
)
async def test_the_database_refuses_to_change_an_audit_record(
    gateway: PersistenceGateway, backend_name: str, statement: str
) -> None:
    """Raw SQL against the audit table is rejected by the database itself."""
    engine = getattr(gateway, "engine", None)
    if engine is None:
        pytest.skip("the append-only trigger is a PostgreSQL object")

    await _seed_event(gateway)

    with pytest.raises(DBAPIError):
        async with engine.begin() as conn:
            await conn.execute(text(statement))

    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        survivor = await uow.audit.get(EVENT_ID)
    assert survivor is not None
    assert survivor.actor_id == "ada"


async def test_a_statement_matching_nothing_is_refused_too(
    gateway: PersistenceGateway, backend_name: str
) -> None:
    """The refusal is per statement, not per row.

    A delete that matched no rows returning success would teach an operator that
    audit rows are deletable and they had simply picked the wrong predicate.
    """
    engine = getattr(gateway, "engine", None)
    if engine is None:
        pytest.skip("the append-only trigger is a PostgreSQL object")

    with pytest.raises(DBAPIError):
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_events WHERE event_id = 'nothing'"))
