"""Shared fixtures for the scheduler suite.

The gateway is the in-memory persistence backend, which has real transactions
and passes the same contract suite as PostgreSQL — so the claiming assertions
below are made against the same behaviour a deployment gets. The pipeline is a
double, because "what an investigation does" is the pipeline's own suite and
repeating it here would make every scheduler test also a test of the ReAct loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.runs.recorder import RunRecorder
from platform.scheduler.executor import ScheduledRunRequest

ORG = "acme"
TEAM = "team-payments"
OTHER_TEAM = "team-search"
PRINCIPAL = "schedule-nightly-dr"

#: A fixed instant, so a claiming assertion is arithmetic rather than a race.
EPOCH = datetime(2026, 3, 2, 1, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


@dataclass(slots=True)
class RecordingPipeline:
    """A pipeline that records what it was asked and answers immediately."""

    summary: str = "Nothing was wrong."
    requests: list[ScheduledRunRequest] = field(default_factory=list)
    fail_with: Exception | None = None
    #: Held open while a request is in flight, so a test can observe two runs
    #: overlapping — which is what a concurrency limit is about.
    gate: asyncio.Event | None = None
    in_flight: int = 0
    peak_in_flight: int = 0

    async def investigate(self, request: ScheduledRunRequest) -> str:
        """Record ``request`` and return a summary."""
        self.requests.append(request)
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            if self.gate is not None:
                await self.gate.wait()
            if self.fail_with is not None:
                raise self.fail_with
            return self.summary
        finally:
            self.in_flight -= 1


@dataclass(slots=True)
class FixedSettings:
    """An effective-configuration resolver returning whatever it was built with."""

    values: Mapping[str, Any] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    async def resolve(self, team_node_id: str) -> Mapping[str, Any]:
        """Return the configuration in force for ``team_node_id``."""
        self.asked.append(team_node_id)
        return dict(self.values)


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Return a persistence gateway holding one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, name="Acme")
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    """Return the tenant scope every test in this suite opens."""
    return TenantScope(org_id=ORG, team_node_id=TEAM)


def recorder_over(store: object, *, prefix: str = "id") -> RunRecorder:
    """Return a recorder with predictable identifiers over ``store``."""
    counter = iter(range(10_000))
    return RunRecorder(
        store=store,  # type: ignore[arg-type]
        clock=lambda: at(),
        ids=lambda: f"{prefix}-{next(counter):04d}",
    )
