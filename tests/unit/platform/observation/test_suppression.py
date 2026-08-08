"""Suppression: what stops a finding, and the record it leaves behind.

Every assertion here is ultimately about the same property. A deployment that
decided not to raise something has to be able to say so — otherwise "nothing
happened" means both "the estate is fine" and "a rule somebody wrote in March
has been silencing this since March", and an operator has no way to tell which.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from platform.incidents.detection import DetectionIntake
from platform.incidents.lifecycle import IncidentLifecycle
from platform.notifications.models import Severity
from platform.observation.detectors.model import Condition, ConditionKind, DetectorDeclaration
from platform.observation.evaluation import EvaluationTick
from platform.observation.suppression import (
    GLOBAL_PAUSE_RULE,
    MAINTENANCE_RULE,
    SuppressionRule,
    Suppressor,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    IncidentQuery,
    IncidentState,
    PersistenceGateway,
    Resource,
    Signal,
    SignalKind,
    TenantScope,
)
from platform.persistence.ports.signal_store import signal_key

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

#: A zone that changes offset, for the window that spans the change.
LONDON = ZoneInfo("Europe/London")


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def sample(minutes: float, value: float, *, resource_id: str = "store-cove") -> Signal:
    """Return one numeric sample."""
    observed_at = at(minutes)
    return Signal(
        signal_id=signal_key("storage.used_percent", resource_id, observed_at),
        name="storage.used_percent",
        resource_id=resource_id,
        source="poller:proxmox",
        kind=SignalKind.NUMBER,
        observed_at=observed_at,
        value=value,
        interval_seconds=60,
    )


def datastore(
    resource_id: str = "store-cove",
    *,
    maintenance_until: datetime | None = None,
    maintenance_reason: str = "",
    team_node_id: str | None = None,
) -> Resource:
    """Return one datastore, optionally in maintenance."""
    return Resource(
        resource_id=resource_id,
        kind="datastore",
        source="proxmox",
        native_id=resource_id,
        team_node_id=team_node_id,
        maintenance_until=maintenance_until,
        maintenance_reason=maintenance_reason,
    )


def near_full() -> DetectorDeclaration:
    """Return the detector every test in this file fires."""
    return DetectorDeclaration(
        detector_id="datastore-near-full",
        name="Datastore near full",
        description="A datastore that fills stops every guest on it at once.",
        resource_kinds=("datastore",),
        signal="storage.used_percent",
        condition=Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=80.0),
        for_seconds=300,
        recovery_seconds=300,
        severity=Severity.CRITICAL,
        team_node_id="team-payments",
    )


@pytest.fixture
async def gateway() -> PersistenceGateway:
    """Return an in-memory gateway with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    return store


# --- Maintenance windows ------------------------------------------------------------


def test_a_maintenance_window_on_the_resource_suppresses_the_detector() -> None:
    """The estate already holds this fact; re-declaring it here would be two answers."""
    covered = datastore(maintenance_until=at(60), maintenance_reason="swapping the disk shelf")
    suppressor = Suppressor(estate={covered.resource_id: covered})

    verdict = suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at())

    assert verdict is not None
    assert verdict.rule_id == MAINTENANCE_RULE
    assert verdict.reason == "swapping the disk shelf"


def test_a_window_that_has_ended_suppresses_nothing() -> None:
    ended = datastore(maintenance_until=at(-1), maintenance_reason="finished an hour ago")
    suppressor = Suppressor(estate={ended.resource_id: ended})

    assert suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at()) is None


def test_a_window_spanning_a_daylight_saving_change_lasts_as_long_as_declared() -> None:
    """Declared in wall-clock terms, compared as instants, so the hour is not lost.

    Europe/London springs forward at 01:00 on 29 March 2026. A window opened at
    00:30 local and declared until 03:30 local covers two wall-clock hours and
    *three* absolute ones, and a comparison between instants is what makes it
    behave the way the operator who typed 03:30 expected.
    """
    opened = datetime(2026, 3, 29, 0, 30, tzinfo=LONDON)
    until = datetime(2026, 3, 29, 3, 30, tzinfo=LONDON)
    covered = datastore(maintenance_until=until, maintenance_reason="a window across the change")
    suppressor = Suppressor(estate={covered.resource_id: covered})

    def at_local(hour: int, minute: int) -> datetime:
        return datetime(2026, 3, 29, hour, minute, tzinfo=LONDON)

    # Before the change, and after it but still inside the declared window.
    assert suppressor.verdict(detector=near_full(), resource_id="store-cove", at=opened)
    assert suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at_local(2, 30))
    # And the moment the operator wrote down, not an hour either side of it.
    assert suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at_local(3, 29))
    assert (
        suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at_local(3, 30))
        is None
    )


# --- Scoped rules -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "covers"),
    [
        (SuppressionRule(rule_id="by-resource", reason="r", resource_ids=("store-cove",)), True),
        (
            SuppressionRule(rule_id="other-resource", reason="r", resource_ids=("store-ridge",)),
            False,
        ),
        (SuppressionRule(rule_id="by-kind", reason="r", kinds=("datastore",)), True),
        (SuppressionRule(rule_id="other-kind", reason="r", kinds=("node",)), False),
        (
            SuppressionRule(
                rule_id="by-detector", reason="r", detector_ids=("datastore-near-full",)
            ),
            True,
        ),
        (SuppressionRule(rule_id="other-detector", reason="r", detector_ids=("x",)), False),
        (SuppressionRule(rule_id="by-team", reason="r", team_node_id="team-payments"), True),
        (SuppressionRule(rule_id="other-team", reason="r", team_node_id="team-search"), False),
    ],
    ids=lambda value: value.rule_id if isinstance(value, SuppressionRule) else str(value),
)
def test_a_rule_is_scopeable_by_resource_kind_detector_and_team(
    rule: SuppressionRule, covers: bool
) -> None:
    resource = datastore(team_node_id="team-payments")
    suppressor = Suppressor(rules=(rule,), estate={resource.resource_id: resource})

    verdict = suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at())

    assert (verdict is not None) is covers


def test_a_rule_is_scopeable_by_time() -> None:
    rule = SuppressionRule(
        rule_id="tonight",
        reason="a planned migration",
        kinds=("datastore",),
        starts_at=at(10),
        ends_at=at(70),
    )
    resource = datastore()
    suppressor = Suppressor(rules=(rule,), estate={resource.resource_id: resource})

    assert suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at(5)) is None
    assert suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at(30))
    assert suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at(70)) is None


def test_a_rule_that_narrows_nothing_covers_nothing() -> None:
    """An accidental global pause nobody can see is what this refuses."""
    rule = SuppressionRule(rule_id="oops", reason="somebody left every field empty")
    suppressor = Suppressor(rules=(rule,))

    assert suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at()) is None


# --- The global pause ---------------------------------------------------------------------


def test_the_global_pause_covers_everything_and_says_why() -> None:
    suppressor = Suppressor(paused=True, pause_reason="migrating the cluster")

    verdict = suppressor.verdict(detector=near_full(), resource_id="anything", at=at())

    assert verdict is not None
    assert verdict.rule_id == GLOBAL_PAUSE_RULE
    assert verdict.reason == "migrating the cluster"


def test_the_pause_is_reported_as_the_reason_rather_than_a_narrower_rule() -> None:
    """Being sent to edit a rack rule when the deployment is paused wastes an hour."""
    rule = SuppressionRule(rule_id="rack-4", reason="a rack migration", kinds=("datastore",))
    resource = datastore()
    suppressor = Suppressor(
        rules=(rule,),
        paused=True,
        pause_reason="everything is paused",
        estate={"store-cove": resource},
    )

    verdict = suppressor.verdict(detector=near_full(), resource_id="store-cove", at=at())

    assert verdict is not None
    assert verdict.rule_id == GLOBAL_PAUSE_RULE


async def test_a_paused_tick_says_it_was_paused(gateway: PersistenceGateway) -> None:
    """A tick that found nothing has to be able to say which kind of nothing."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-5, 91.0), sample(-2, 92.0), sample(0, 95.0)])

        outcome = await EvaluationTick(
            detectors=(near_full(),),
            suppressor=Suppressor(paused=True, pause_reason="migrating the cluster"),
        ).run(uow.signals, resources=(datastore(),), now=at())

    assert outcome.paused
    assert outcome.pause_reason == "migrating the cluster"
    assert outcome.findings == ()
    assert len(outcome.suppressed) == 1


# --- Recorded, never silent ------------------------------------------------------------------


async def test_a_firing_inside_a_maintenance_window_is_recorded_as_suppressed(
    gateway: PersistenceGateway,
) -> None:
    """SC-004. It is in the incident list, marked, countable, and searchable."""
    covered = datastore(maintenance_until=at(60), maintenance_reason="swapping the disk shelf")

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-5, 91.0), sample(-2, 92.0), sample(0, 95.0)])
        outcome = await EvaluationTick(
            detectors=(near_full(),),
            suppressor=Suppressor(estate={covered.resource_id: covered}),
        ).run(uow.signals, resources=(covered,), now=at())

        report = await DetectionIntake(
            lifecycle=IncidentLifecycle(store=uow.incidents),
            detectors={"datastore-near-full": near_full()},
        ).absorb(outcome, resources=(covered,), now=at())

        listed = await uow.incidents.query(IncidentQuery())

    assert outcome.findings == ()
    assert report.opened == ()
    assert len(report.suppressed) == 1
    assert report.suppressed[0].state is IncidentState.SUPPRESSED
    assert report.suppressed[0].suppressed_by == MAINTENANCE_RULE
    assert len(listed) == 1


async def test_a_suppression_is_countable_rather_than_an_absence(
    gateway: PersistenceGateway,
) -> None:
    """A rule that is too broad has to be a number, not a thing nobody notices."""
    covered = datastore(maintenance_until=at(60), maintenance_reason="a very broad window")

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-5, 91.0), sample(0, 95.0)])
        outcome = await EvaluationTick(
            detectors=(near_full(),),
            suppressor=Suppressor(estate={covered.resource_id: covered}),
        ).run(uow.signals, resources=(covered,), now=at())
        await DetectionIntake(
            lifecycle=IncidentLifecycle(store=uow.incidents),
            detectors={"datastore-near-full": near_full()},
        ).absorb(outcome, resources=(covered,), now=at())

        suppressed = await uow.incidents.query(IncidentQuery(states=(IncidentState.SUPPRESSED,)))

    assert len(suppressed) == 1
    assert suppressed[0].close_reason == "a very broad window"


async def test_an_uncovered_resource_still_raises_while_a_covered_one_does_not(
    gateway: PersistenceGateway,
) -> None:
    """Suppression is per subject, so a window on one machine does not silence the rack."""
    covered = datastore("store-cove", maintenance_until=at(60), maintenance_reason="disk swap")
    uncovered = datastore("store-ridge")

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(
            [
                sample(minute, 95.0, resource_id=resource.resource_id)
                for resource in (covered, uncovered)
                for minute in (-5, -2, 0)
            ]
        )
        outcome = await EvaluationTick(
            detectors=(near_full(),),
            suppressor=Suppressor(estate={covered.resource_id: covered}),
        ).run(uow.signals, resources=(covered, uncovered), now=at())

        report = await DetectionIntake(
            lifecycle=IncidentLifecycle(store=uow.incidents),
            detectors={"datastore-near-full": near_full()},
        ).absorb(outcome, resources=(covered, uncovered), now=at())

    assert [entry.resource_id for entry in outcome.findings] == ["store-ridge"]
    assert len(report.opened) == 1
    assert report.opened[0].subject_ids == ("store-ridge",)
    assert len(report.suppressed) == 1
