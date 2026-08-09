"""SC-002, over the whole shipped set: it fires on the condition and not on health.

This is the test that decides whether shipping forty-six detectors is a good
idea or a bad one. Each of them is a chance to be wrong in two directions — a
detector that never fires is a detector somebody trusts and should not, and one
that fires on a healthy cluster is the reason the whole thing gets turned off in
week one.

Both halves are driven through the *real* evaluator over the real declaration,
built from the real condition. Nothing here reimplements a comparison, so a
detector whose clear value sits on the wrong side of its firing value, or whose
state transition names no state, fails here rather than in somebody's homelab.

The fixture values live on the detector rather than in this file, and they are
required fields with no default. That is deliberate: a fixture table beside the
set is a table somebody forgets to extend, and the point of SC-002 is that the
forty-seventh detector cannot be added without both readings.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.guardian.catalogue import SHIPPED_DETECTORS, Reading, ShippedDetector
from platform.observation.detectors.conditions import Verdict, evaluate
from platform.observation.detectors.model import ConditionKind
from platform.observation.signals import SignalWindow
from platform.persistence.ports import Signal, SignalKind
from platform.persistence.ports.signal_store import signal_key

pytestmark = pytest.mark.contract

EPOCH = datetime(2026, 8, 7, 3, 14, tzinfo=UTC)

#: How far apart the synthesised samples are. Matches the interval the shipped
#: signal sources declare, so a window that covers a detector's duration here
#: covers it in a real deployment too.
STEP_SECONDS = 300

IDS = [detector.detector_id for detector in SHIPPED_DETECTORS]

RESOURCE = "res-fixture"


def _series(detector: ShippedDetector, reading: Reading) -> tuple[Signal, ...]:
    """Return samples holding ``reading`` for longer than ``detector`` requires.

    A rate-of-change detector gets a ramp instead of a flat line, because the
    reading for one of those is a slope: a flat series at any value has a rate
    of zero, and asserting that a growth detector does not fire on it would
    prove nothing at all.
    """
    span = max(detector.for_seconds, detector.recovery_seconds) + STEP_SECONDS
    count = max(3, span // STEP_SECONDS + 1)
    ramp = detector.condition_kind is ConditionKind.RATE_OF_CHANGE

    samples: list[Signal] = []
    for index in range(count):
        offset = (count - 1 - index) * STEP_SECONDS
        observed_at = EPOCH - timedelta(seconds=offset)
        value = reading.value * (index * STEP_SECONDS / 60.0) if ramp else reading.value
        samples.append(
            Signal(
                signal_id=signal_key(detector.signal, RESOURCE, observed_at),
                name=detector.signal,
                resource_id=RESOURCE,
                source="guardian",
                kind=SignalKind.STATE if reading.state else SignalKind.NUMBER,
                observed_at=observed_at,
                value=value,
                state=reading.state,
                interval_seconds=STEP_SECONDS,
            )
        )
    return tuple(samples)


def _window(detector: ShippedDetector, reading: Reading) -> SignalWindow:
    """Return a window over a series holding ``reading``."""
    samples = _series(detector, reading)
    return SignalWindow(
        name=detector.signal,
        resource_id=RESOURCE,
        opened_at=samples[0].observed_at,
        closed_at=EPOCH,
        samples=samples,
        last_seen=samples[-1],
    )


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_every_shipped_detector_fires_on_a_fixture_of_its_own_condition(
    detector: ShippedDetector,
) -> None:
    """SC-002, first half. A detector that cannot fire is worse than no detector,
    because somebody is relying on it."""
    observation = evaluate(detector.declaration(), _window(detector, detector.firing), now=EPOCH)

    assert observation.verdict is Verdict.FIRING, (
        f"{detector.detector_id} did not fire on {detector.firing.describe()}: "
        f"{observation.verdict} — {observation.detail}"
    )


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_no_shipped_detector_fires_on_a_fixture_of_health(
    detector: ShippedDetector,
) -> None:
    """SC-002, second half, and the one that decides whether the first week is
    informative or noisy."""
    observation = evaluate(detector.declaration(), _window(detector, detector.healthy), now=EPOCH)

    assert not observation.is_finding, (
        f"{detector.detector_id} fired on {detector.healthy.describe()}, which is a "
        f"healthy reading: {observation.detail}"
    )


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_a_healthy_fixture_reaches_a_verdict_rather_than_saying_it_cannot_tell(
    detector: ShippedDetector,
) -> None:
    """Not firing because the window was too short is not the same as not firing.

    A detector that reported INSUFFICIENT against a full window of healthy
    readings would pass the test above while proving nothing, which is exactly
    the shape a shipped set drifts into as durations are lengthened.
    """
    observation = evaluate(detector.declaration(), _window(detector, detector.healthy), now=EPOCH)

    assert observation.verdict is not Verdict.INSUFFICIENT, (
        f"{detector.detector_id} could not reach a verdict about a healthy reading: "
        f"{observation.detail}"
    )


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_the_two_fixtures_are_actually_different_readings(
    detector: ShippedDetector,
) -> None:
    """A pair of identical fixtures passes both halves above and proves nothing."""
    assert detector.firing != detector.healthy, detector.detector_id


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_a_detector_reports_the_reading_that_decided_it(
    detector: ShippedDetector,
) -> None:
    """Article I. A finding with no observation behind it is an assertion."""
    observation = evaluate(detector.declaration(), _window(detector, detector.firing), now=EPOCH)

    assert observation.evidence, detector.detector_id
    assert detector.signal in observation.evidence, detector.detector_id
