"""What happens to the record when the database will not take it, and how it leaves.

Two requirements meet here and both are about the audit trail's worst day.
A failed write is a serious error: the record goes somewhere durable, somebody is
alerted, and the caller is told. And the trail has to be exportable in a form a
SIEM ingests, because it is exempt from every retention sweep and an operator's
only way to bound its growth is to move it.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from platform.identity.audit.export import CONTENT_TYPE, AuditExport
from platform.identity.audit.recorder import (
    AuditContext,
    AuditFallback,
    AuditRecorder,
    as_record,
)
from platform.identity.errors import AuditWriteFailed
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    PersistenceGateway,
    TenantScope,
)

ORG = "acme"
AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
SCOPE = TenantScope(org_id=ORG)


def context() -> AuditContext:
    """Return an ordinary acting context."""
    return AuditContext(actor_kind=ActorKind.USER, actor_id="ada", source_address="203.0.113.7")


async def gateway() -> FakePersistence:
    """Return a persistence gateway with the tenant created."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return store


class BrokenGateway:
    """A gateway whose transactions always fail, for the write-failure path."""

    def begin(self, scope: TenantScope) -> object:
        """Raise when the caller tries to open a unit of work."""
        raise OSError("the database is unreachable")


# --- The durable fallback --------------------------------------------


async def test_a_failed_write_raises_rather_than_being_swallowed(tmp_path: Path) -> None:
    """The caller must not report success it cannot substantiate."""
    recorder = AuditRecorder(
        gateway=BrokenGateway(),  # type: ignore[arg-type]
        fallback=AuditFallback(path=tmp_path / "audit-fallback.jsonl"),
        clock=lambda: AT,
    )

    with pytest.raises(AuditWriteFailed):
        await recorder.record(
            SCOPE,
            context(),
            action="config.field.set",
            resource_kind="config_node",
            resource_id="x",
        )


async def test_a_failed_write_leaves_the_record_on_disk(tmp_path: Path) -> None:
    """The record survives the outage that stopped it being stored."""
    path = tmp_path / "nested" / "audit-fallback.jsonl"
    recorder = AuditRecorder(
        gateway=BrokenGateway(),  # type: ignore[arg-type]
        fallback=AuditFallback(path=path),
        clock=lambda: AT,
    )

    with pytest.raises(AuditWriteFailed):
        await recorder.record(
            SCOPE,
            context(),
            action="config.field.set",
            resource_kind="config_node",
            resource_id="x",
        )

    written = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(written) == 1
    assert written[0]["org_id"] == ORG
    assert written[0]["action"] == "config.field.set"
    assert written[0]["actor_id"] == "ada"


async def test_a_failed_write_raises_an_alert(tmp_path: Path) -> None:
    """Somebody has to be told; the file alone is a record nobody reads."""
    alerted: list[tuple[str, AuditEvent]] = []
    recorder = AuditRecorder(
        gateway=BrokenGateway(),  # type: ignore[arg-type]
        fallback=AuditFallback(path=tmp_path / "audit-fallback.jsonl"),
        clock=lambda: AT,
        on_failure=lambda org_id, event, _failure: alerted.append((org_id, event)),
    )

    with pytest.raises(AuditWriteFailed):
        await recorder.record(
            SCOPE, context(), action="token.revoke", resource_kind="api_token", resource_id="t1"
        )

    assert [org for org, _ in alerted] == [ORG]


async def test_the_fallback_names_the_file_in_the_error(tmp_path: Path) -> None:
    """An operator reading the exception should not have to guess where to look."""
    path = tmp_path / "audit-fallback.jsonl"
    recorder = AuditRecorder(
        gateway=BrokenGateway(),  # type: ignore[arg-type]
        fallback=AuditFallback(path=path),
        clock=lambda: AT,
    )

    with pytest.raises(AuditWriteFailed) as raised:
        await recorder.record(
            SCOPE,
            context(),
            action="config.field.set",
            resource_kind="config_node",
            resource_id="x",
        )

    assert str(path) in str(raised.value)


async def test_an_unwritable_fallback_still_alerts_rather_than_crashing(tmp_path: Path) -> None:
    """The last line cannot itself be the thing that loses the record silently."""
    unwritable = tmp_path / "audit-fallback.jsonl"
    unwritable.mkdir()  # a directory where a file is expected

    recorder = AuditRecorder(
        gateway=BrokenGateway(),  # type: ignore[arg-type]
        fallback=AuditFallback(path=unwritable),
        clock=lambda: AT,
    )

    with pytest.raises(AuditWriteFailed):
        await recorder.record(
            SCOPE,
            context(),
            action="config.field.set",
            resource_kind="config_node",
            resource_id="x",
        )


async def test_a_successful_write_leaves_the_fallback_empty(tmp_path: Path) -> None:
    """The positive control: the fallback is for failures and nothing else."""
    path = tmp_path / "audit-fallback.jsonl"
    recorder = AuditRecorder(
        gateway=await gateway(), fallback=AuditFallback(path=path), clock=lambda: AT
    )

    await recorder.record(
        SCOPE, context(), action="config.field.set", resource_kind="config_node", resource_id="x"
    )
    assert not path.exists()


# --- Export --------------------------------------------------


async def seed(store: PersistenceGateway, count: int) -> Sequence[AuditEvent]:
    """Append ``count`` events, one minute apart, and return them oldest first."""
    events = [
        AuditEvent(
            event_id=f"evt-{index:03d}",
            occurred_at=AT + timedelta(minutes=index),
            actor_kind=ActorKind.USER,
            actor_id="ada",
            action="config.field.set",
            resource_kind="config_node",
            resource_id=f"node-{index}",
            outcome=AuditOutcome.ALLOWED,
            detail={"field": "policies.masking.level"},
        )
        for index in range(count)
    ]
    async with store.begin(SCOPE) as uow:
        for event in events:
            await uow.audit.append(event)
    return events


async def test_the_export_is_newline_delimited_json() -> None:
    """A standard SIEM ingests it without being told about us."""
    store = await gateway()
    await seed(store, 3)

    buffer = io.StringIO()
    written = await AuditExport(gateway=store).write(SCOPE, buffer)

    lines = buffer.getvalue().splitlines()
    assert written == 3
    assert len(lines) == 3
    for line in lines:
        record = json.loads(line)
        assert record["org_id"] == ORG
        assert set(record) >= {"event_id", "occurred_at", "actor_id", "action", "outcome"}


async def test_the_export_covers_every_record_across_pages() -> None:
    """The paging is the part that loses records if it is written carelessly."""
    store = await gateway()
    seeded = await seed(store, 25)

    exporter = AuditExport(gateway=store, page_size=4)
    exported = [event.event_id async for event in exporter.events(SCOPE)]

    assert sorted(exported) == sorted(event.event_id for event in seeded)


async def test_the_export_emits_each_record_once() -> None:
    """Re-reading the boundary instant must not duplicate what sits on it."""
    store = await gateway()
    await seed(store, 25)

    exporter = AuditExport(gateway=store, page_size=4)
    exported = [event.event_id async for event in exporter.events(SCOPE)]

    assert len(exported) == len(set(exported))


async def test_the_export_honours_a_window() -> None:
    """An operator archiving last month asks for last month."""
    store = await gateway()
    await seed(store, 10)

    exporter = AuditExport(gateway=store, page_size=3)
    window = [
        event.event_id
        async for event in exporter.events(
            SCOPE, since=AT + timedelta(minutes=3), until=AT + timedelta(minutes=6)
        )
    ]

    assert sorted(window) == ["evt-003", "evt-004", "evt-005"]


async def test_the_export_of_an_empty_window_produces_nothing() -> None:
    """Not an error, and not a header nobody asked for."""
    store = await gateway()
    buffer = io.StringIO()
    assert await AuditExport(gateway=store).write(SCOPE, buffer) == 0
    assert buffer.getvalue() == ""


async def test_the_export_streams_a_line_at_a_time() -> None:
    """What an HTTP response needs, so a month of history is not held in memory."""
    store = await gateway()
    await seed(store, 5)

    lines = [line async for line in AuditExport(gateway=store).lines(SCOPE)]
    assert len(lines) == 5
    assert all(line.endswith("\n") for line in lines)


def test_the_export_and_the_fallback_write_the_same_shape() -> None:
    """An operator reconciling the two after an outage has enough to do."""
    event = AuditEvent(
        event_id="evt-1",
        occurred_at=AT,
        actor_kind=ActorKind.USER,
        actor_id="ada",
        action="config.field.set",
        resource_kind="config_node",
        resource_id="x",
    )
    assert set(as_record(ORG, event)) == {
        "org_id",
        "event_id",
        "occurred_at",
        "actor_kind",
        "actor_id",
        "action",
        "resource_kind",
        "resource_id",
        "outcome",
        "detail",
    }


def test_the_export_declares_a_content_type_a_siem_recognises() -> None:
    """Named once, because a surface should not have to know the format."""
    assert CONTENT_TYPE == "application/x-ndjson"
