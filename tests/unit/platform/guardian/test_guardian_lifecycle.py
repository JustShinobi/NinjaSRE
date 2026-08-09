"""The deployment's own size, cost, upgrades, restarts, and where it is running.

Five small modules in one file because they answer one question between them:
whether the thing an operator installed on their own machine behaves itself —
stays inside the size it promised, costs the cluster little, survives being
upgraded and rebooted, and is honest about being a guest of what it watches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.guardian import MAX_CLUSTER_CALLS_PER_MINUTE
from platform.guardian.catalogue import SHIPPED_DETECTORS, SignalOrigin, detector_by_id
from platform.guardian.declared import (
    DeclaredIntent,
    DeclaredResource,
    redirect_if_declared,
    unexpectedly_stopped,
)
from platform.guardian.footprint import Footprint, UsageSample, assess
from platform.guardian.load import declare_load, shipped_sources
from platform.guardian.resumption import ResumedWork
from platform.guardian.selfaware import locate, problems_affecting_self
from platform.guardian.upgrade import compare, fingerprint, fingerprints
from platform.guardian.windows import ScheduledActivity, offer_windows
from platform.persistence.ports.estate_repository import Resource

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 7, 3, 14, tzinfo=UTC)


# -- footprint ---------------------------------------------------------------------


def _soak(hours: float, *, mib: float, growth: float = 0.0) -> list[UsageSample]:
    """Return a soak of ``hours`` at ``mib``, drifting by ``growth`` over the run."""
    steps = max(4, int(hours * 4))
    return [
        UsageSample(
            at=NOW - timedelta(hours=hours) + timedelta(hours=hours * index / steps),
            memory_mib=mib + growth * index / steps,
        )
        for index in range(steps + 1)
    ]


def test_a_soak_that_stayed_inside_the_footprint_says_so() -> None:
    """NFR-001 and SC-001."""
    verdict = assess(_soak(30, mib=1_400))

    assert verdict.within
    assert verdict.long_enough
    assert verdict.conclusive


def test_a_soak_that_breached_names_when() -> None:
    samples = _soak(30, mib=1_400)
    samples[10] = UsageSample(at=samples[10].at, memory_mib=9_000)

    verdict = assess(samples)

    assert not verdict.within
    assert verdict.breached_at == samples[10].at
    assert "Exceeded" in verdict.describe(Footprint())


def test_a_short_run_reports_that_it_cannot_conclude_rather_than_that_all_is_well() -> None:
    """A soak that ran for four minutes has established a fact about four minutes."""
    verdict = assess(_soak(0.1, mib=1_400))

    assert verdict.within
    assert not verdict.long_enough
    assert not verdict.conclusive
    assert "no verdict yet" in verdict.describe(Footprint())


def test_a_rising_floor_is_reported_even_when_nothing_breached() -> None:
    """A peak can be one investigation; a floor that climbed cannot."""
    verdict = assess(_soak(30, mib=1_000, growth=400))

    assert verdict.within
    assert verdict.memory_growth_mib > 300


def test_measuring_nothing_concludes_nothing() -> None:
    verdict = assess([])

    assert not verdict.conclusive
    assert "nothing to conclude" in verdict.describe(Footprint())


# -- load ---------------------------------------------------------------------------


def test_detection_stays_inside_the_call_rate_it_declares() -> None:
    """NFR-002 and T-055, measured from the shipped set rather than configured."""
    declaration = declare_load()

    assert declaration.within_declared_bound
    assert 0 < declaration.cluster_calls_per_minute <= MAX_CLUSTER_CALLS_PER_MINUTE


def test_several_detectors_over_one_reading_are_one_poll() -> None:
    """The high and critical datastore detectors read the same number."""
    sources = shipped_sources()
    signals = [source.signal for source in sources]

    assert len(signals) == len(set(signals))
    assert len(sources) < len(SHIPPED_DETECTORS)


def test_readings_the_operator_s_own_monitoring_publishes_cost_the_cluster_nothing() -> None:
    """Which is what makes "add ten more exporter detectors" a free decision."""
    declaration = declare_load()
    published = [source for source in declaration.sources if not source.costs_the_cluster]

    assert published
    assert all(source.origin is SignalOrigin.PUBLISHED for source in published)
    assert declaration.published_calls_per_minute > 0


def test_the_declared_load_says_what_it_costs_in_a_sentence() -> None:
    assert "calls a minute" in declare_load().describe()


# -- upgrade ------------------------------------------------------------------------


def test_a_release_that_changed_nothing_reports_nothing() -> None:
    """SC-011's second half. A report that always says something is one nobody reads."""
    report = compare(fingerprints())

    assert not report.anything_changed
    assert "No shipped detector's definition changed" in report.describe()


def test_a_changed_threshold_is_reported_by_name() -> None:
    stored = dict(fingerprints())
    stored["storage-datastore-usage-high"] = "0000deadbeef"

    report = compare(stored)

    assert [change.detector_id for change in report.changed] == ["storage-datastore-usage-high"]


def test_a_change_to_a_detector_the_operator_overrode_is_flagged_as_such() -> None:
    """The case they most need to look at: their number may now contradict the new one."""
    stored = dict(fingerprints())
    stored["storage-datastore-usage-high"] = "0000deadbeef"

    report = compare(stored, overridden=("storage-datastore-usage-high",))

    assert report.changed[0].overridden
    assert "override" in report.changed[0].describe()


def test_an_added_and_a_removed_detector_are_both_named() -> None:
    stored = dict(fingerprints())
    stored.pop("host-bridge-down")
    stored["storage-something-retired"] = "aaaabbbbcccc"

    report = compare(stored)

    assert "host-bridge-down" in report.added
    assert "storage-something-retired" in report.removed


def test_the_first_start_after_an_older_release_does_not_report_everything_as_new() -> None:
    """A report listing forty-six additions is one nobody reads — including next
    time, when it means something."""
    report = compare({})

    assert not report.anything_changed


def test_rewording_a_rationale_is_not_a_definition_change() -> None:
    """A release that improves prose without moving a number has changed nothing an
    operator needs to review."""
    from dataclasses import replace

    detector = detector_by_id("storage-datastore-usage-high")
    assert detector is not None
    reworded = replace(detector, rationale=detector.rationale + " Reworded for clarity.")

    assert fingerprint(reworded) == fingerprint(detector)


def test_the_upgrade_report_carries_what_it_preserved() -> None:
    """FR-006. An upgrade that emptied the estate would otherwise be discovered by
    an operator wondering why the console is blank."""
    report = compare(fingerprints(), preserved={"resources": 84, "incidents": 12, "policies": 3})

    assert report.to_record()["preserved"]["resources"] == 84


# -- restart ------------------------------------------------------------------------


def test_a_clean_restart_reports_all_three_things_back_and_nothing_lost() -> None:
    """SC-010."""
    resumed = ResumedWork(
        observer_running=True,
        scheduler_running=True,
        obligations_owed=4,
        obligations_reclaimed=2,
        incidents_open=7,
        incidents_open_before=7,
        resumed_at=NOW,
    )

    assert resumed.everything_resumed
    assert resumed.lost_incidents == 0
    assert "Nothing was lost" in resumed.describe()


def test_an_observer_that_did_not_come_back_is_the_failure_that_looks_healthy() -> None:
    resumed = ResumedWork(observer_running=False, scheduler_running=True)

    assert not resumed.everything_resumed
    assert "looks exactly like a healthy deployment" in resumed.describe()


def test_an_incident_that_did_not_survive_the_restart_is_counted() -> None:
    resumed = ResumedWork(
        observer_running=True,
        scheduler_running=True,
        incidents_open=5,
        incidents_open_before=7,
    )

    assert resumed.lost_incidents == 2
    assert not resumed.everything_resumed


# -- self-awareness -----------------------------------------------------------------


def _resource(resource_id: str, name: str, parent: str = "") -> Resource:
    """Return one estate resource, as discovery would have written it."""
    return Resource(
        resource_id=resource_id,
        source="proxmox",
        native_id=name,
        kind="container",
        display_name=name,
        parent_id=parent or None,
    )


def test_a_deployment_running_as_a_guest_of_what_it_watches_says_so() -> None:
    """SC-012, first half."""
    placement = locate("ninjasre", resources=[_resource("res-1", "ninjasre", "res-node-pve01")])

    assert placement.on_managed_estate
    assert placement.node_id == "res-node-pve01"
    assert "inside the estate it watches" in placement.describe()


def test_a_deployment_on_hardware_the_cluster_does_not_own_says_that_instead() -> None:
    placement = locate("thinkpad", resources=[_resource("res-1", "plex")])

    assert not placement.on_managed_estate
    assert "does not take the guardian with it" in placement.describe()


def test_a_problem_about_the_node_underneath_is_reported_as_affecting_itself() -> None:
    """SC-012, second half, and the one that matters: a health report that said
    "healthy" here would be worse than one that said nothing."""
    placement = locate("ninjasre", resources=[_resource("res-1", "ninjasre", "res-node-pve01")])

    found = problems_affecting_self(
        placement,
        [("inc-9", "pve01 is unreachable", ("res-node-pve01", "res-77"))],
    )

    assert len(found) == 1
    assert "the node this deployment runs on" in found[0].describe()


def test_a_problem_about_the_deployment_itself_is_named_as_that() -> None:
    placement = locate("ninjasre", resources=[_resource("res-1", "ninjasre", "res-node-pve01")])

    found = problems_affecting_self(placement, [("inc-3", "res-1 filesystem full", ("res-1",))])

    assert found[0].relation == "this deployment itself"


def test_a_deployment_outside_the_estate_has_no_self_affecting_problems() -> None:
    placement = locate("thinkpad", resources=[])

    assert problems_affecting_self(placement, [("inc-1", "anything", ("res-9",))]) == ()


# -- freeze windows -----------------------------------------------------------------


def test_a_nightly_backup_is_offered_as_a_window_with_a_margin_either_side() -> None:
    """T-047: the operator did not have to know they needed one."""
    from datetime import time

    offer = offer_windows([ScheduledActivity(name="pve02-baseline", starts_at=time(7, 0))])

    assert offer.has_offer
    assert offer.windows[0].start == "06:30"
    assert offer.windows[0].end == "08:30"
    assert "leaves a guest locked" in offer.windows[0].reason


def test_a_window_that_starts_before_midnight_wraps_rather_than_clamping() -> None:
    """These windows are around backups, and backups run at two in the morning."""
    from datetime import time

    offer = offer_windows([ScheduledActivity(name="postgres", starts_at=time(0, 15))])

    assert offer.windows[0].start == "23:45"


def test_a_disabled_job_produces_no_window() -> None:
    """Freezing around a job that never runs is a permanent freeze nobody can account for."""
    from datetime import time

    offer = offer_windows(
        [ScheduledActivity(name="pve01-baseline", starts_at=time(8, 0), enabled=False)]
    )

    assert not offer.has_offer


def test_an_activity_too_long_to_freeze_around_is_reported_and_not_offered() -> None:
    """Six hours is where a freeze stops being a window and becomes a posture."""
    from datetime import time

    offer = offer_windows(
        [ScheduledActivity(name="full-estate", starts_at=time(2, 0), minutes=600)]
    )

    assert not offer.has_offer
    assert offer.too_long[0][0] == "full-estate"
    assert "switching autonomy off by another name" in offer.summarise()


def test_a_cluster_with_no_schedules_is_told_there_is_nothing_to_offer() -> None:
    assert "no window to offer" in offer_windows([]).summarise()


# -- the declarative control plane -----------------------------------------------------


def _intent() -> DeclaredIntent:
    """Return an inventory declaring one guest that should run and owning its network."""
    return DeclaredIntent(
        source="the operator's infrastructure repository",
        resources=(
            DeclaredResource(
                native_id="ct-115",
                expected_running=True,
                role="dns",
                owns=("network", "interfaces"),
            ),
            DeclaredResource(native_id="ct-161", expected_running=True),
        ),
    )


def test_the_control_plane_supplies_the_expectation_the_api_cannot() -> None:
    """ "A guest stopped that was expected running" needs somebody to have expected it."""
    stopped = unexpectedly_stopped(
        _intent(), running=["ct-161"], known=["ct-115", "ct-161", "ct-999"]
    )

    assert stopped == ("ct-115",)


def test_a_guest_nobody_declared_being_stopped_is_not_a_deviation_from_anything() -> None:
    stopped = unexpectedly_stopped(_intent(), running=[], known=["ct-999"])

    assert stopped == ()


def test_a_remediation_the_control_plane_owns_is_proposed_rather_than_applied() -> None:
    """FR-030. A second writer is how drift becomes an outage."""
    proposal = redirect_if_declared(
        _intent(),
        native_id="ct-115",
        property_name="network",
        intended_change="reattach the guest to vmbr0",
    )

    assert proposal is not None
    assert proposal.to_record()["apply_here"] is False
    assert "would revert it" in proposal.describe()


def test_a_remediation_the_control_plane_does_not_own_is_left_alone() -> None:
    """Most remediations touch runtime state no repository owns, and redirecting
    those would make the control plane's existence a reason to do nothing."""
    assert (
        redirect_if_declared(
            _intent(),
            native_id="ct-115",
            property_name="power_state",
            intended_change="start the guest",
        )
        is None
    )


def test_with_no_control_plane_configured_nothing_is_redirected() -> None:
    assert (
        redirect_if_declared(
            DeclaredIntent(),
            native_id="ct-115",
            property_name="network",
            intended_change="anything",
        )
        is None
    )
