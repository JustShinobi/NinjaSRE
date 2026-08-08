"""Retention: signals live exactly as long as some detector can still reach them.

The property worth testing is not that old rows go — any sweep does that. It is
that the horizon is *derived from the declarations*, so an operator who
lengthens a window does not also have to remember to lengthen retention. If they
did, the detector would silently never fire, and there would be nothing to
distinguish that from an estate with nothing wrong.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.observation import DEFAULT_SIGNAL_RETENTION_SECONDS
from platform.notifications.models import Severity
from platform.observation.detectors.model import Condition, ConditionKind, DetectorDeclaration
from platform.observation.retention import SignalRetention
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import Signal, SignalKind, SignalQuery, TenantScope
from platform.persistence.ports.signal_store import signal_key

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def detector(*, for_seconds: int, recovery_seconds: int = 300) -> DetectorDeclaration:
    """Return a detector with the declared windows and nothing else interesting."""
    return DetectorDeclaration(
        detector_id=f"d-{for_seconds}",
        name="d",
        description="a detector with a window",
        resource_kinds=(),
        signal="storage.used_percent",
        condition=Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=80.0),
        for_seconds=for_seconds,
        recovery_seconds=recovery_seconds,
        severity=Severity.HIGH,
    )


def sample(minutes: float) -> Signal:
    """Return one sample at ``minutes``."""
    observed_at = at(minutes)
    return Signal(
        signal_id=signal_key("storage.used_percent", "store-cove", observed_at),
        name="storage.used_percent",
        resource_id="store-cove",
        source="poller:proxmox",
        kind=SignalKind.NUMBER,
        observed_at=observed_at,
        value=50.0,
        interval_seconds=60,
    )


def test_the_horizon_is_the_longest_window_any_detector_declares() -> None:
    retention = SignalRetention(
        detectors=(
            detector(for_seconds=300),
            detector(for_seconds=3_600, recovery_seconds=600),
            detector(for_seconds=900),
        )
    )

    assert retention.horizon_seconds == 3_600


def test_a_recovery_window_counts_as_much_as_a_firing_one() -> None:
    """A detector that can fire and never clear is worse than one that cannot fire."""
    retention = SignalRetention(detectors=(detector(for_seconds=300, recovery_seconds=7_200),))

    assert retention.horizon_seconds == 7_200


def test_a_disabled_detector_still_counts_towards_the_horizon() -> None:
    """Re-enabling something that then cannot fire for an hour is the surprise this avoids."""
    retention = SignalRetention(detectors=(replace(detector(for_seconds=7_200), enabled=False),))

    assert retention.horizon_seconds == 7_200


def test_a_deployment_with_no_detectors_still_bounds_its_table() -> None:
    assert SignalRetention().horizon_seconds == DEFAULT_SIGNAL_RETENTION_SECONDS


async def test_the_sweep_keeps_what_the_longest_window_still_reaches() -> None:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")

    retention = SignalRetention(detectors=(detector(for_seconds=1_800),))

    async with store.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-120), sample(-45), sample(-20), sample(-1)])

        removed = await retention.sweep(uow.signals, now=at())
        left = await uow.signals.window(SignalQuery())

    assert removed == 2
    assert [entry.observed_at for entry in left] == [at(-20), at(-1)]


async def test_lengthening_a_window_lengthens_retention_without_a_second_setting() -> None:
    """The whole point: one number, declared once, on the detector."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")

    async with store.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-90)])

        await SignalRetention(detectors=(detector(for_seconds=7_200),)).sweep(uow.signals, now=at())

    async with store.begin(TenantScope(org_id="acme")) as uow:
        assert len(await uow.signals.window(SignalQuery())) == 1
