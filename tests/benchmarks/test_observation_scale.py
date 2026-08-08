"""Ten thousand resources and a hundred detectors, evaluated inside the budget.

The budget is in ``config.constants.observation`` rather than here, so the
number and the assertion cannot drift apart. What this file adds is the *shape*
the number was measured against, because a budget without one is not a budget:

- ten thousand resources across ten kinds, a thousand each;
- a hundred detectors, each scoped to one kind and one of ten signals, so ten
  detectors share every signal — which is what a real set looks like and what
  makes the read-per-signal design worth having;
- three samples per series inside the window, the smallest number that can
  satisfy a duration.

That is a hundred thousand evaluations and ten queries. A tick that read per
detector rather than per signal would make it a hundred queries for the same
work, which is the design this measurement exists to keep honest.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.observation import (
    OBSERVATION_TICK_BUDGET_DETECTORS,
    OBSERVATION_TICK_BUDGET_RESOURCES,
    OBSERVATION_TICK_BUDGET_SECONDS,
)
from platform.notifications.models import Severity
from platform.observation.detectors.model import Condition, ConditionKind, DetectorDeclaration
from platform.observation.evaluation import EvaluationTick
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import Resource, Signal, SignalKind, TenantScope
from platform.persistence.ports.signal_store import signal_key

pytestmark = pytest.mark.benchmark

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

#: Ten kinds, a thousand resources each. Detectors are scoped to a kind, which
#: is what a real set does and what keeps the evaluation count at a hundred
#: thousand rather than a million.
KINDS = tuple(f"kind-{index}" for index in range(10))

#: Ten signals, ten detectors each. Sharing a signal is the common case — a
#: warning threshold and a critical one over the same measurement — and it is
#: the case the per-signal read exists for.
SIGNALS = tuple(f"signal.{index}" for index in range(10))


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def estate() -> tuple[Resource, ...]:
    """Return ten thousand resources across ten kinds."""
    per_kind = OBSERVATION_TICK_BUDGET_RESOURCES // len(KINDS)
    return tuple(
        Resource(
            resource_id=f"{kind}-{index:04d}",
            kind=kind,
            source="benchmark",
            native_id=f"{kind}/{index}",
        )
        for kind in KINDS
        for index in range(per_kind)
    )


def detectors() -> tuple[DetectorDeclaration, ...]:
    """Return a hundred detectors, ten per signal, each scoped to one kind."""
    return tuple(
        DetectorDeclaration(
            detector_id=f"d-{index:03d}",
            name=f"detector {index}",
            description="a detector declared for the scale measurement",
            resource_kinds=(KINDS[index % len(KINDS)],),
            signal=SIGNALS[index % len(SIGNALS)],
            condition=Condition(
                kind=ConditionKind.THRESHOLD,
                fire_value=90.0 + (index % 5),
                clear_value=80.0,
            ),
            for_seconds=300,
            recovery_seconds=300,
            severity=Severity.HIGH,
        )
        for index in range(OBSERVATION_TICK_BUDGET_DETECTORS)
    )


def history(resources: tuple[Resource, ...]) -> list[Signal]:
    """Return three samples per resource for the signal its kind's detectors read."""
    samples: list[Signal] = []
    for resource in resources:
        name = SIGNALS[KINDS.index(resource.kind) % len(SIGNALS)]
        for minute, value in ((-5.0, 91.0), (-2.0, 92.0), (0.0, 93.0)):
            observed_at = at(minute)
            samples.append(
                Signal(
                    signal_id=signal_key(name, resource.resource_id, observed_at),
                    name=name,
                    resource_id=resource.resource_id,
                    source="benchmark",
                    kind=SignalKind.NUMBER,
                    observed_at=observed_at,
                    value=value,
                    interval_seconds=60,
                )
            )
    return samples


async def test_one_tick_over_ten_thousand_resources_stays_inside_its_budget() -> None:
    """SC-010, against the store that serves it rather than against a list."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")

    resources = estate()
    async with store.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(history(resources))

    tick = EvaluationTick(detectors=detectors())

    async with store.begin(TenantScope(org_id="acme")) as uow:
        started = time.perf_counter()
        outcome = await tick.run(uow.signals, resources=resources, now=at())
        elapsed = time.perf_counter() - started

    assert outcome.subjects == OBSERVATION_TICK_BUDGET_RESOURCES
    assert outcome.detectors == OBSERVATION_TICK_BUDGET_DETECTORS
    # Ten detectors per signal, a thousand resources per kind, one kind each.
    assert len(outcome.evaluated) == OBSERVATION_TICK_BUDGET_DETECTORS * (
        OBSERVATION_TICK_BUDGET_RESOURCES // len(KINDS)
    )
    assert outcome.failures == ()
    assert elapsed < OBSERVATION_TICK_BUDGET_SECONDS, (
        f"one tick over {OBSERVATION_TICK_BUDGET_RESOURCES} resources and "
        f"{OBSERVATION_TICK_BUDGET_DETECTORS} detectors took {elapsed:.2f}s, past the "
        f"{OBSERVATION_TICK_BUDGET_SECONDS}s declared in config.constants.observation"
    )
