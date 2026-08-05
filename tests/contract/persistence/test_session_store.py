"""Contract: resumable session state."""

from __future__ import annotations

import pytest
from conftest import at

from platform.persistence.ports import PersistenceGateway, SessionRecord, TenantScope

pytestmark = pytest.mark.contract


def session(session_id: str, *, status: str = "suspended", minutes: float = 0.0) -> SessionRecord:
    """Return a session record at a fixed offset."""
    return SessionRecord(
        session_id=session_id,
        status=status,
        run_id="run-1",
        payload={"transcript": [], "iteration": 3},
        updated_at=at(minutes),
    )


async def test_a_session_round_trips(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.sessions.save(session("s-1"))
        found = await uow.sessions.load("s-1")

    assert found is not None
    assert found.payload["iteration"] == 3


async def test_the_payload_stays_opaque(gateway: PersistenceGateway, scope: TenantScope) -> None:
    # The store does not know what a session is. That is what lets feature 004
    # add a field without a migration here.
    async with gateway.begin(scope) as uow:
        await uow.sessions.save(
            SessionRecord(
                session_id="s-1",
                status="running",
                payload={"a_field_this_store_has_never_heard_of": [1, 2, 3]},
            )
        )
        found = await uow.sessions.load("s-1")

    assert found is not None
    assert found.payload["a_field_this_store_has_never_heard_of"] == [1, 2, 3]


async def test_the_last_write_wins(gateway: PersistenceGateway, scope: TenantScope) -> None:
    # Correct here and nowhere else in this package: a session is one run's own
    # state, so there is no second writer to lose a race against.
    async with gateway.begin(scope) as uow:
        await uow.sessions.save(session("s-1", status="running"))
        await uow.sessions.save(session("s-1", status="completed"))
        found = await uow.sessions.load("s-1")

    assert found is not None
    assert found.status == "completed"


async def test_deleting_reports_whether_it_was_there(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.sessions.save(session("s-1"))

        assert await uow.sessions.delete("s-1") is True
        assert await uow.sessions.delete("s-1") is False


async def test_the_longest_waiting_session_comes_back_first(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.sessions.save(session("s-new", minutes=10))
        await uow.sessions.save(session("s-old", minutes=0))
        await uow.sessions.save(session("s-done", status="completed", minutes=5))

        resumable = await uow.sessions.list_resumable(statuses=("suspended",))
        everything = await uow.sessions.list_resumable()

    assert [record.session_id for record in resumable] == ["s-old", "s-new"]
    assert len(everything) == 3
