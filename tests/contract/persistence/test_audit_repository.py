"""Contract: the audit trail, which nothing edits and no sweep deletes."""

from __future__ import annotations

import pytest
from conftest import at

from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from platform.persistence.errors import BoundExceeded, DuplicateRecord
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    AuditRepository,
    PersistenceGateway,
    TenantScope,
)

pytestmark = pytest.mark.contract


def event(event_id: str, *, minutes: float = 0.0, action: str = "capability.invoke") -> AuditEvent:
    """Return an audit event at a fixed offset."""
    return AuditEvent(
        event_id=event_id,
        occurred_at=at(minutes),
        actor_kind=ActorKind.AGENT,
        actor_id="run-1",
        action=action,
        resource_kind="deployment",
        resource_id="checkout",
    )


async def test_the_port_offers_no_way_to_change_or_remove_an_event() -> None:
    """FR-022's exemption, held at the type level rather than by a constant.

    ``RETENTION_EXEMPT_DATA_CLASSES`` can be edited. A method that was never
    written has to be written, and writing it is a review nobody would pass.
    """
    surface = {name for name in dir(AuditRepository) if not name.startswith("_")}

    assert surface == {"append", "get", "query", "count"}


async def test_an_event_round_trips(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.audit.append(event("e-1"))
        found = await uow.audit.get("e-1")

    assert found is not None
    assert found.outcome is AuditOutcome.ALLOWED


async def test_appending_the_same_event_twice_is_refused(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Either a retry the caller should have made idempotent, or a bug. Treating
    # it as an overwrite would hide the second.
    async with gateway.begin(scope) as uow:
        await uow.audit.append(event("e-1"))

        with pytest.raises(DuplicateRecord):
            await uow.audit.append(event("e-1"))


async def test_events_come_back_most_recent_first(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.audit.append(event("e-1", minutes=0))
        await uow.audit.append(event("e-2", minutes=5))
        found = await uow.audit.query()

    assert [item.event_id for item in found] == ["e-2", "e-1"]


async def test_filters_narrow_and_absent_filters_do_not(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.audit.append(event("e-1", action="capability.invoke"))
        await uow.audit.append(event("e-2", minutes=1, action="approval.decide"))

        assert len(await uow.audit.query()) == 2
        assert [e.event_id for e in await uow.audit.query(action="approval.decide")] == ["e-2"]
        assert await uow.audit.query(actor_id="somebody-else") == ()


async def test_the_window_is_half_open_so_consecutive_windows_tile(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.audit.append(event("e-1", minutes=0))
        await uow.audit.append(event("e-2", minutes=10))

        assert await uow.audit.count(since=at(0), until=at(10)) == 1
        assert await uow.audit.count(since=at(10), until=at(20)) == 1


async def test_a_page_larger_than_the_bound_is_refused_not_shortened(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A caller that asked for 500 and received 200 cannot tell that from there
    # being 200.
    async with gateway.begin(scope) as uow:
        with pytest.raises(BoundExceeded) as failure:
            await uow.audit.query(limit=MAX_QUERY_PAGE_SIZE + 1)

    assert failure.value.constant == "MAX_QUERY_PAGE_SIZE"
