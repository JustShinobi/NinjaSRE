"""Detectors: the declaration, the four condition kinds, and what each does at its boundary.

The boundary cases are the file. A detector that fires one sample early is a
false alarm; one that fires one sample late is a missed incident; and one that
cannot tell "we have not been watching long enough" from "nothing is wrong"
reports health it has not established.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.observation import FLAP_CROSSING_THRESHOLD
from core.capability.metadata import SideEffectLevel
from platform.config_service.schema.policies import DetectorSettings, ObservationPolicySettings
from platform.notifications.models import Severity
from platform.observation.detectors import config as detector_config
from platform.observation.detectors.conditions import Verdict, evaluate
from platform.observation.detectors.model import (
    Comparison,
    Condition,
    ConditionKind,
    DetectorDeclaration,
    GroupingKey,
)
from platform.observation.detectors.registry import DetectorRegistry
from platform.observation.errors import (
    DetectorInvalid,
    DetectorMayNotAct,
    ObservationBoundExceeded,
    UnknownDetector,
)
from platform.observation.signals import SignalWindow, windows
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import Signal, SignalKind, TenantScope
from platform.persistence.ports.signal_store import signal_key

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def sample(
    minutes: float,
    value: float = 0.0,
    *,
    name: str = "storage.used_percent",
    resource_id: str = "store-cove",
    state: str = "",
    interval_seconds: int = 60,
) -> Signal:
    """Return one stored sample."""
    observed_at = at(minutes)
    return Signal(
        signal_id=signal_key(name, resource_id, observed_at),
        name=name,
        resource_id=resource_id,
        source="poller:proxmox",
        kind=SignalKind.STATE if state else SignalKind.NUMBER,
        observed_at=observed_at,
        value=value,
        state=state,
        interval_seconds=interval_seconds,
    )


def window(*samples: Signal, opened: float = -10.0, closed: float = 0.0) -> SignalWindow:
    """Return the one window these samples make, empty when there are none."""
    built = windows(samples, opened_at=at(opened), closed_at=at(closed), latest=samples)
    if built:
        return built[0]
    return SignalWindow(
        name="storage.used_percent",
        resource_id="store-cove",
        opened_at=at(opened),
        closed_at=at(closed),
    )


def detector(
    condition: Condition,
    *,
    detector_id: str = "datastore-near-full",
    signal: str = "storage.used_percent",
    for_seconds: int = 300,
    recovery_seconds: int = 300,
    grouping_key: GroupingKey = GroupingKey.DETECTOR,
    capabilities: tuple[str, ...] = (),
) -> DetectorDeclaration:
    """Return a detector over ``condition``."""
    return DetectorDeclaration(
        detector_id=detector_id,
        name="Datastore near full",
        description="A datastore that fills stops every guest on it at once.",
        resource_kinds=("datastore",),
        signal=signal,
        condition=condition,
        for_seconds=for_seconds,
        recovery_seconds=recovery_seconds,
        severity=Severity.CRITICAL,
        grouping_key=grouping_key,
        capabilities=capabilities,
    )


# --- The declaration ---------------------------------------------------------------


def test_a_detector_without_a_reason_is_refused() -> None:
    """The rationale is what somebody needs when deciding the threshold is wrong."""
    with pytest.raises(DetectorInvalid, match="description"):
        DetectorDeclaration(
            detector_id="d",
            name="d",
            description="",
            resource_kinds=(),
            signal="s",
            condition=Condition(kind=ConditionKind.THRESHOLD),
            for_seconds=300,
            recovery_seconds=300,
        )


def test_a_duration_below_the_floor_is_refused() -> None:
    """A detector with no duration fires on one sample, which is a crossing."""
    with pytest.raises(ObservationBoundExceeded, match="MIN_DETECTOR_DURATION_SECONDS"):
        detector(Condition(kind=ConditionKind.THRESHOLD), for_seconds=1)


def test_a_window_longer_than_retention_is_refused() -> None:
    with pytest.raises(ObservationBoundExceeded, match="MAX_DETECTOR_WINDOW_SECONDS"):
        detector(Condition(kind=ConditionKind.THRESHOLD), for_seconds=999_999)


def test_a_clear_value_on_the_wrong_side_would_clear_before_it_opened() -> None:
    with pytest.raises(DetectorInvalid, match="clear before it opened"):
        detector(
            Condition(
                kind=ConditionKind.THRESHOLD,
                comparison=Comparison.ABOVE,
                fire_value=90.0,
                clear_value=95.0,
            )
        )


def test_a_state_transition_has_to_name_the_state_that_fires() -> None:
    with pytest.raises(DetectorInvalid, match="to_state"):
        detector(Condition(kind=ConditionKind.STATE_TRANSITION))


# --- Threshold, at its boundary ------------------------------------------------------


def test_a_threshold_holding_for_its_duration_fires() -> None:
    rule = detector(
        Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=85.0),
        for_seconds=300,
    )
    held = window(sample(-6, 91.0), sample(-3, 92.0), sample(0, 93.0))

    assert evaluate(rule, held, now=at()).verdict is Verdict.FIRING


def test_a_threshold_crossed_and_not_yet_held_is_pending_rather_than_firing() -> None:
    """Firing one sample early is a false alarm, and pending is a real answer."""
    rule = detector(
        Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=85.0),
        for_seconds=300,
    )
    just_crossed = window(sample(-1, 91.0), sample(0, 92.0))

    assert evaluate(rule, just_crossed, now=at()).verdict is Verdict.PENDING


def test_a_threshold_crossed_and_recovered_inside_the_duration_never_fires() -> None:
    rule = detector(
        Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=85.0),
        for_seconds=300,
    )
    blipped = window(sample(-6, 50.0), sample(-3, 91.0), sample(0, 50.0))

    assert evaluate(rule, blipped, now=at()).verdict is not Verdict.FIRING


def test_a_value_exactly_on_the_threshold_does_not_fire() -> None:
    """Above means above. An inclusive boundary makes ninety per cent an incident."""
    rule = detector(
        Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=85.0),
        for_seconds=60,
    )
    exactly = window(sample(-5, 90.0), sample(0, 90.0))

    assert evaluate(rule, exactly, now=at()).verdict is not Verdict.FIRING


def test_an_empty_window_is_insufficient_rather_than_clear() -> None:
    """Reporting health nobody established is the failure this feature removes."""
    rule = detector(Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=85.0))

    assert evaluate(rule, window(), now=at()).verdict is Verdict.INSUFFICIENT


# --- Hysteresis ----------------------------------------------------------------------


def test_a_value_between_the_two_thresholds_neither_fires_nor_clears() -> None:
    """The whole of hysteresis, in one assertion."""
    rule = detector(
        Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=80.0),
        for_seconds=60,
        recovery_seconds=60,
    )
    between = window(sample(-5, 85.0), sample(0, 85.0))

    assert evaluate(rule, between, now=at()).verdict is Verdict.HOLDING


def test_a_value_back_under_the_clear_threshold_clears() -> None:
    rule = detector(
        Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=80.0),
        recovery_seconds=300,
    )
    recovered = window(sample(-6, 70.0), sample(-3, 71.0), sample(0, 72.0))

    assert evaluate(rule, recovered, now=at()).verdict is Verdict.CLEAR


def test_a_flapping_signal_reports_flapping_rather_than_firing_per_crossing() -> None:
    """Three incidents about one oscillation are three interruptions and one fact."""
    rule = detector(
        Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=80.0),
        for_seconds=60,
    )
    oscillating = window(
        sample(-10, 95.0),
        sample(-9, 70.0),
        sample(-8, 95.0),
        sample(-7, 70.0),
        sample(-6, 95.0),
        sample(0, 70.0),
    )

    verdict = evaluate(rule, oscillating, now=at())

    assert verdict.verdict is Verdict.FLAPPING
    assert int(verdict.evidence["crossings"]) >= FLAP_CROSSING_THRESHOLD


# --- Absence ---------------------------------------------------------------------------


def test_a_series_that_stopped_reporting_fires() -> None:
    rule = detector(
        Condition(kind=ConditionKind.ABSENCE),
        detector_id="signal-stopped",
        for_seconds=300,
    )
    quiet = windows((), opened_at=at(-10), closed_at=at(), latest=(sample(-30, 50.0),))[0]

    assert evaluate(rule, quiet, now=at()).verdict is Verdict.FIRING


def test_a_series_nobody_has_ever_measured_does_not_fire() -> None:
    """Otherwise every resource a second integration does not cover is an incident."""
    rule = detector(Condition(kind=ConditionKind.ABSENCE), detector_id="signal-stopped")
    never = SignalWindow(
        name="storage.used_percent",
        resource_id="store-cove",
        opened_at=at(-10),
        closed_at=at(),
    )

    assert evaluate(rule, never, now=at()).verdict is Verdict.INSUFFICIENT


def test_a_source_that_promised_nothing_is_never_absent() -> None:
    rule = detector(Condition(kind=ConditionKind.ABSENCE), detector_id="signal-stopped")
    unpromised = windows(
        (), opened_at=at(-10), closed_at=at(), latest=(sample(-600, 50.0, interval_seconds=0),)
    )[0]

    assert evaluate(rule, unpromised, now=at()).verdict is Verdict.CLEAR


def test_a_series_that_is_arriving_clears() -> None:
    rule = detector(Condition(kind=ConditionKind.ABSENCE), detector_id="signal-stopped")
    arriving = window(sample(-1, 50.0))

    assert evaluate(rule, arriving, now=at()).verdict is Verdict.CLEAR


# --- Rate of change ---------------------------------------------------------------------


def test_a_rate_above_the_declared_change_per_minute_fires() -> None:
    rule = detector(
        Condition(kind=ConditionKind.RATE_OF_CHANGE, fire_value=1.0, clear_value=1.0),
        for_seconds=300,
    )
    climbing = window(sample(-10, 50.0), sample(-5, 60.0), sample(0, 70.0))

    assert evaluate(rule, climbing, now=at()).verdict is Verdict.FIRING


def test_a_rate_under_the_declared_change_does_not_fire() -> None:
    rule = detector(
        Condition(kind=ConditionKind.RATE_OF_CHANGE, fire_value=5.0, clear_value=5.0),
        for_seconds=60,
    )
    creeping = window(sample(-10, 50.0), sample(-5, 51.0), sample(0, 52.0))

    assert evaluate(rule, creeping, now=at()).verdict is not Verdict.FIRING


# --- State transition ----------------------------------------------------------------


def test_entering_the_named_state_fires_once_it_has_held() -> None:
    rule = detector(
        Condition(kind=ConditionKind.STATE_TRANSITION, to_state="unhealthy"),
        signal="estate.health",
        for_seconds=300,
    )
    gone = window(
        sample(-10, state="unhealthy", name="estate.health"),
        sample(-5, state="unhealthy", name="estate.health"),
        sample(0, state="unhealthy", name="estate.health"),
    )

    assert evaluate(rule, gone, now=at()).verdict is Verdict.FIRING


def test_a_declared_previous_state_is_required_when_it_is_declared() -> None:
    rule = detector(
        Condition(kind=ConditionKind.STATE_TRANSITION, to_state="unhealthy", from_state="healthy"),
        signal="estate.health",
        for_seconds=60,
    )
    from_maintenance = window(
        sample(-10, state="maintenance", name="estate.health"),
        sample(-5, state="unhealthy", name="estate.health"),
        sample(0, state="unhealthy", name="estate.health"),
    )

    assert evaluate(rule, from_maintenance, now=at()).verdict is not Verdict.FIRING


# --- Every verdict carries its evidence ------------------------------------------------


def test_a_finding_carries_the_values_it_was_reached_from() -> None:
    """Article I: a conclusion carries the observations that support it."""
    rule = detector(
        Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=85.0),
        for_seconds=300,
    )
    held = window(sample(-6, 91.0), sample(0, 93.0))

    observation = evaluate(rule, held, now=at())

    assert observation.evidence["storage.used_percent"] == "93"
    assert observation.detail


# --- Configuration ------------------------------------------------------------------------


def test_a_team_declares_a_detector_without_new_code() -> None:
    settings = ObservationPolicySettings(
        detectors=(
            DetectorSettings(
                detector_id="datastore-near-full",
                signal="storage.used_percent",
                name="Datastore near full",
                description="A datastore that fills stops every guest on it.",
                fire_value=90.0,
                clear_value=80.0,
                for_seconds=300,
                recovery_seconds=300,
                severity="critical",
            ),
        )
    )

    resolved = detector_config.read(settings)

    assert [entry.detector_id for entry in resolved.detectors] == ["datastore-near-full"]
    assert resolved.detectors[0].severity is Severity.CRITICAL
    assert resolved.problems == ()


def test_one_bad_detector_does_not_take_the_good_ones_with_it() -> None:
    """Four saves to find four mistakes is how an operator learns to stop reading errors."""
    settings = ObservationPolicySettings(
        detectors=(
            DetectorSettings(
                detector_id="good",
                signal="storage.used_percent",
                description="fine",
                fire_value=90.0,
                clear_value=80.0,
            ),
            DetectorSettings(
                detector_id="inverted",
                signal="storage.used_percent",
                description="clear above fire",
                fire_value=90.0,
                clear_value=95.0,
            ),
        )
    )

    resolved = detector_config.read(settings)

    assert [entry.detector_id for entry in resolved.detectors] == ["good"]
    assert [entry[0] for entry in resolved.problems] == ["inverted"]


def test_an_undeclared_configuration_field_is_refused() -> None:
    """The closed schema is what keeps configuration from becoming key-value storage."""
    with pytest.raises(ValueError, match="not permitted"):
        DetectorSettings(detector_id="d", signal="s", thershold=90.0)  # type: ignore[call-arg]


def test_a_condition_kind_the_evaluator_does_not_implement_is_refused() -> None:
    with pytest.raises(ValueError, match="must be one of"):
        DetectorSettings(detector_id="d", signal="s", kind="regex")


def test_a_global_pause_stops_every_detector_without_unconfiguring_one() -> None:
    settings = ObservationPolicySettings(
        detectors=(
            DetectorSettings(
                detector_id="good", signal="s", description="fine", fire_value=1.0, clear_value=1.0
            ),
        ),
        paused=True,
        pause_reason="migrating the cluster",
    )

    resolved = detector_config.read(settings)

    assert resolved.enabled == ()
    assert len(resolved.detectors) == 1
    assert resolved.pause_reason == "migrating the cluster"


# --- The registry ---------------------------------------------------------------------------


@dataclass
class StubLevels:
    """A capability catalogue that answers whatever a test declares."""

    levels: dict[str, SideEffectLevel]

    def level_of(self, capability: str) -> SideEffectLevel | None:
        """Return the declared level, or ``None``."""
        return self.levels.get(capability)


def test_a_detector_may_not_reference_a_capability_that_writes() -> None:
    """A detector that can act is an actuator with none of the controls in front of it."""
    levels = StubLevels({"proxmox.restart_guest": SideEffectLevel.WRITE_REVERSIBLE})

    with pytest.raises(DetectorMayNotAct, match="write_reversible"):
        DetectorRegistry().register(
            detector(
                Condition(kind=ConditionKind.THRESHOLD, fire_value=1.0, clear_value=1.0),
                capabilities=("proxmox.restart_guest",),
            ),
            levels=levels,
        )


def test_a_capability_nobody_declared_is_refused_rather_than_assumed_safe() -> None:
    with pytest.raises(DetectorMayNotAct, match="undeclared"):
        DetectorRegistry().register(
            detector(
                Condition(kind=ConditionKind.THRESHOLD, fire_value=1.0, clear_value=1.0),
                capabilities=("nobody.declared_this",),
            ),
            levels=StubLevels({}),
        )


def test_a_read_only_capability_is_accepted() -> None:
    levels = StubLevels({"proxmox.read_storage": SideEffectLevel.READ})

    registered = DetectorRegistry().register(
        detector(
            Condition(kind=ConditionKind.THRESHOLD, fire_value=1.0, clear_value=1.0),
            capabilities=("proxmox.read_storage",),
        ),
        levels=levels,
    )

    assert registered.capabilities == ("proxmox.read_storage",)


def test_disabling_a_detector_takes_it_out_of_the_next_tick() -> None:
    registry = DetectorRegistry.of(
        [detector(Condition(kind=ConditionKind.THRESHOLD, fire_value=1.0, clear_value=1.0))]
    )

    registry.set_enabled("datastore-near-full", enabled=False)

    assert registry.enabled() == ()
    assert len(registry.all()) == 1


def test_an_operation_naming_a_detector_nothing_declared_is_an_error() -> None:
    with pytest.raises(UnknownDetector):
        DetectorRegistry().get("nothing-declared-this")


async def test_a_dry_run_against_history_reports_what_would_have_fired_and_fires_nothing() -> None:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")

    registry = DetectorRegistry.of(
        [
            detector(
                Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=80.0),
                for_seconds=300,
            )
        ]
    )

    async with store.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-10, 91.0), sample(-5, 92.0), sample(0, 93.0)])

        run = await registry.dry_run("datastore-near-full", uow.signals, now=at())

    assert run.would_fire
    assert [entry.verdict for entry in run.findings] == [Verdict.FIRING]
