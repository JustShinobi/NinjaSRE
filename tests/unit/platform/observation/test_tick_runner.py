"""Polling the sources a deployment composed, and storing what they said.

``OBSERVATION_TICK_JOB_KIND`` exists, ``tick_job`` builds a job of that kind,
``Poller`` rations one source, and nothing ever constructed a poller or ran a
tick. So a deployment with a metrics source composed still had no numbers: the
job was claimed, found unrunnable, and rescheduled.

Two properties are the reason this is a runner rather than a loop in the
dispatcher:

**The resources are read fresh each tick.** A guest discovered by the last sweep
has to be polled by this one, and a map built at composition would be one sweep
behind for ever.

**A source that fails does not take the tick with it.** One unreachable metrics
system must not stop the others from being read, or a deployment loses every
signal to whichever vendor is having an afternoon.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.observation.tick import ObservationTickRunner

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)


class _Source:
    """A signal source that answers with whatever it was given."""

    def __init__(self, readings: tuple[object, ...] = (), fails: bool = False) -> None:
        self.readings = readings
        self.fails = fails
        self.asked: list[tuple[str, ...]] = []

    @property
    def declaration(self) -> object:
        from platform.observation.sources.port import SignalDeclaration

        return SignalDeclaration(
            source="prometheus", signals=("cpu",), interval_seconds=60, max_provider_calls=3
        )

    async def read(self, *, resource_ids: tuple[str, ...], at: datetime, budget: object) -> object:
        from platform.observation.sources.port import SignalPage

        del at, budget
        self.asked.append(resource_ids)
        if self.fails:
            raise RuntimeError("the metrics system is unreachable")
        return SignalPage(readings=self.readings, provider_calls=1)


def _reading(resource_id: str, value: float) -> object:
    from platform.observation.sources.port import SignalReading

    return SignalReading(name="cpu", resource_id=resource_id, value=value)


class _Store:
    def __init__(self) -> None:
        self.appended: list[object] = []

    async def append(self, signals: object) -> object:
        self.appended.extend(signals)
        return tuple(signals)


def test_the_store_a_deployment_actually_has_satisfies_what_a_tick_asks_for() -> None:
    """The narrow port has to be a protocol, not a concrete class.

    Declared as a dataclass, ``SignalWriter`` described the right shape and
    nothing could satisfy it: the real store does not inherit from it, so the
    only thing that could ever be passed was a subclass nobody writes. The
    runner typechecked against a port with no implementations.
    """
    from platform.observation.tick import SignalWriter
    from platform.persistence.postgres.repositories.signal_store import PostgresSignalStore

    # Checked by mypy as well as at runtime: this is the assignment the job
    # runner makes, and the one the gate rejected.
    writer: type[SignalWriter] = PostgresSignalStore

    assert issubclass(writer, SignalWriter)


async def test_a_tick_polls_the_sources_and_stores_what_they_returned() -> None:
    source = _Source(readings=(_reading("res-a", 0.5),))
    store = _Store()

    stored = await ObservationTickRunner(
        sources=(source,),  # type: ignore[arg-type]
        resources=lambda: ("res-a", "res-b"),
        store=store,  # type: ignore[arg-type]
    ).tick(now=NOW)

    assert source.asked == [("res-a", "res-b")]
    assert stored == 1
    assert len(store.appended) == 1


async def test_the_resources_are_read_fresh_each_tick() -> None:
    """A guest the last sweep discovered has to be polled by this one."""
    source = _Source()
    estate = ["res-a"]
    runner = ObservationTickRunner(
        sources=(source,),  # type: ignore[arg-type]
        resources=lambda: tuple(estate),
        store=_Store(),  # type: ignore[arg-type]
    )

    await runner.tick(now=NOW)
    estate.append("res-b")
    await runner.tick(now=NOW)

    assert source.asked == [("res-a",), ("res-a", "res-b")]


async def test_a_source_that_fails_does_not_take_the_tick_with_it() -> None:
    """One vendor having an afternoon must not cost every other signal."""
    broken = _Source(fails=True)
    working = _Source(readings=(_reading("res-a", 0.5),))
    store = _Store()

    stored = await ObservationTickRunner(
        sources=(broken, working),  # type: ignore[arg-type]
        resources=lambda: ("res-a",),
        store=store,  # type: ignore[arg-type]
    ).tick(now=NOW)

    assert stored == 1
    assert len(store.appended) == 1


async def test_an_estate_with_nothing_in_it_asks_nobody() -> None:
    """A poll over no resources is a provider call that cannot answer."""
    source = _Source()

    stored = await ObservationTickRunner(
        sources=(source,),  # type: ignore[arg-type]
        resources=tuple,
        store=_Store(),  # type: ignore[arg-type]
    ).tick(now=NOW)

    assert source.asked == []
    assert stored == 0


async def test_a_deployment_with_no_sources_ticks_without_error() -> None:
    """Composing none is the ordinary state of a deployment nothing is pointed at."""
    stored = await ObservationTickRunner(
        sources=(),
        resources=lambda: ("res-a",),
        store=_Store(),  # type: ignore[arg-type]
    ).tick(now=NOW)

    assert stored == 0
