"""Telling a person who is not on a rota, and being noticed when you stop.

The three failures this file is about all look like success from inside the
deployment: a storm that arrived as forty messages nobody read, a resolution
that was never sent because the original was never acknowledged, and a guardian
that stopped and therefore raised nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.guardian import DIGEST_THRESHOLD, HEARTBEAT_INTERVAL_SECONDS
from config.constants.notifications import (
    DESTINATION_DISCORD,
    DESTINATION_EMAIL,
    DESTINATION_TELEGRAM,
)
from platform.guardian.heartbeat import (
    Heartbeat,
    HeartbeatReadiness,
    HeartbeatSchedule,
)
from platform.guardian.notices import (
    DIGEST_SUBJECT,
    Digest,
    EscalationBound,
    Finding,
    digest_or_individually,
)
from platform.notifications.models import Outcome, Severity

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 7, 3, 14, tzinfo=UTC)


def a_finding(
    detector_id: str = "storage-datastore-usage-critical",
    *,
    minutes_ago: float = 1.0,
    severity: Severity = Severity.HIGH,
    done: str = "",
    not_done_because: str = "",
    needed: str = "free space on TeraChad",
) -> Finding:
    """Return one finding, at a chosen distance from now."""
    return Finding(
        detector_id=detector_id,
        title="TeraChad is at 96%",
        happened="TeraChad reached 96% of 7452 GiB and has been there for twenty minutes",
        resource="res-terachad",
        severity=severity,
        at=NOW - timedelta(minutes=minutes_ago),
        done=done,
        not_done_because=not_done_because,
        needed=needed,
    )


# -- what a notification says ------------------------------------------------------


def test_a_message_says_what_happened_what_was_done_what_was_not_and_what_is_needed() -> None:
    """FR-022, all four, in that order."""
    message = a_finding(
        done="nothing",
        not_done_because="the deployment is in propose-only, which you chose",
    ).message()

    assert "96%" in message
    assert "Done:" in message
    assert "Not done:" in message
    assert "Needed from you:" in message


def test_the_what_was_not_done_part_is_present_even_when_nothing_was_done() -> None:
    """Under propose-only the honest answer to "what was done" is "nothing", and a
    message that stopped there reads as a failure rather than as the posture."""
    message = a_finding().message()

    assert "nothing has been executed" in message


def test_a_finding_becomes_one_notification_through_the_ordinary_type() -> None:
    notification = a_finding().notification(team_node_id="home")

    assert notification.severity is Severity.HIGH
    assert notification.team_node_id == "home"
    assert notification.subject.startswith("storage-datastore-usage-critical")


# -- resolution after the fact -----------------------------------------------------


def test_a_resolution_is_its_own_message_rather_than_a_state_change() -> None:
    """FR-023 and SC-009. The operator may never have seen the first one."""
    resolution = a_finding().resolution()

    assert resolution.outcome is Outcome.RESOLVED
    assert resolution.title.startswith("Resolved:")
    assert "nothing for you to do" in resolution.message


def test_a_resolution_shares_the_original_s_subject_so_it_lands_in_one_thread() -> None:
    finding = a_finding()

    assert finding.resolution().subject == finding.notification().subject


def test_a_resolution_is_low_severity_because_it_is_not_an_interruption() -> None:
    assert a_finding(severity=Severity.CRITICAL).resolution().severity is Severity.LOW


# -- digestion ---------------------------------------------------------------------


def test_two_findings_are_two_notifications() -> None:
    """Two things a few minutes apart are two things, and the operator wants both."""
    sent = digest_or_individually([a_finding("storage-a"), a_finding("storage-b")], now=NOW)

    assert len(sent) == 2


def test_a_storm_becomes_exactly_one_digest() -> None:
    """SC-008. Not a rate limit — a rate limit throws away the later items, and the
    later items are usually the ones that explain the earlier ones."""
    findings = [a_finding(f"guest-{index}") for index in range(20)]

    sent = digest_or_individually(findings, now=NOW)

    assert len(sent) == 1
    assert sent[0].subject == DIGEST_SUBJECT
    assert "20 findings" in sent[0].title


def test_the_digest_threshold_is_where_the_behaviour_changes() -> None:
    below = digest_or_individually(
        [a_finding(f"guest-{index}") for index in range(DIGEST_THRESHOLD - 1)], now=NOW
    )
    at_it = digest_or_individually(
        [a_finding(f"guest-{index}") for index in range(DIGEST_THRESHOLD)], now=NOW
    )

    assert len(below) == DIGEST_THRESHOLD - 1
    assert len(at_it) == 1


def test_a_digest_takes_the_worst_severity_rather_than_an_average() -> None:
    """One critical finding among twenty makes a critical notification."""
    findings = [a_finding(f"guest-{index}", severity=Severity.LOW) for index in range(9)]
    findings.append(a_finding("cluster-quorum-lost", severity=Severity.CRITICAL))

    sent = digest_or_individually(findings, now=NOW)

    assert sent[0].severity is Severity.CRITICAL


def test_a_digest_names_what_it_can_and_says_how_much_it_did_not() -> None:
    """A digest nobody can read on a phone is one nobody reads."""
    digest = Digest(
        findings=tuple(a_finding(f"guest-{index}") for index in range(30)),
        opened_at=NOW - timedelta(minutes=4),
        closed_at=NOW,
    )

    body = digest.message()

    assert "30 findings" in body
    assert "and 20 more" in body


def test_findings_from_outside_the_window_do_not_make_a_storm() -> None:
    """The question is whether what is happening *now* is a storm."""
    findings = [a_finding(f"guest-{index}", minutes_ago=90) for index in range(20)]
    findings.append(a_finding("storage-now", minutes_ago=1))

    sent = digest_or_individually(findings, now=NOW)

    assert len(sent) == 1
    assert sent[0].subject != DIGEST_SUBJECT


# -- escalation --------------------------------------------------------------------


def test_escalation_ends_and_says_that_it_has() -> None:
    """FR-025. There is no rota, so an escalation that repeats for ever is one the
    only recipient learns to filter — which costs them the next one too."""
    bound = EscalationBound()

    assert not bound.exhausted(0)
    assert bound.exhausted(bound.rounds)
    assert "last message" in bound.final_message("TeraChad is at 96%")


def test_the_escalation_bound_records_why_it_is_bounded() -> None:
    assert EscalationBound().to_record()["ends"] is True


# -- the heartbeat -----------------------------------------------------------------


def test_a_heartbeat_carries_counts_rather_than_the_estate() -> None:
    """The destination is usually a third party, and a fifteen-minute inventory
    leaving the operator's network is not what they asked for."""
    payload = Heartbeat(sequence=41, at=NOW, open_incidents=3).to_payload()

    assert set(payload) == {
        "deployment",
        "sequence",
        "at",
        "healthy",
        "open_incidents",
        "degraded_because",
    }


def test_silence_is_believed_only_after_more_than_one_missed_interval() -> None:
    """An external watcher that cried wolf on every reboot is one that gets muted,
    at which point the dead-man's switch is off and looks on."""
    schedule = HeartbeatSchedule()
    one_missed = NOW - timedelta(seconds=HEARTBEAT_INTERVAL_SECONDS * 1.5)
    long_gone = NOW - timedelta(seconds=HEARTBEAT_INTERVAL_SECONDS * 4)

    assert not schedule.is_overdue(last_seen=one_missed, now=NOW)
    assert schedule.is_overdue(last_seen=long_gone, now=NOW)


def test_the_schedule_can_state_itself_to_whatever_is_watching() -> None:
    described = HeartbeatSchedule().describe_for_watcher()

    assert "minutes" in described
    assert "Alert if" in described


def test_a_deployment_on_the_estate_with_nowhere_to_push_is_warned_specifically() -> None:
    """FR-029: the one combination in which it cannot report its own death."""
    readiness = HeartbeatReadiness(destination_configured=False, on_managed_estate=True)

    assert readiness.is_the_dangerous_combination
    assert not readiness.can_report_its_own_death
    assert "cannot report its own death" in readiness.warning()


def test_a_deployment_off_the_estate_with_nowhere_to_push_is_still_warned() -> None:
    """Less severely, and still: nothing outside would notice it stopping."""
    readiness = HeartbeatReadiness(destination_configured=False, on_managed_estate=False)

    assert not readiness.is_the_dangerous_combination
    assert readiness.warning()


def test_a_configured_destination_is_the_case_with_nothing_to_say() -> None:
    readiness = HeartbeatReadiness(destination_configured=True, on_managed_estate=True)

    assert readiness.can_report_its_own_death
    assert readiness.warning() == ""


def test_the_personal_channels_are_first_class_destinations() -> None:
    """FR-021: no corporate account required. These are the three the feature names,
    and they are the platform's own destinations rather than a second list."""
    from config.constants.notifications import DESTINATION_CLASS_OF

    for destination in (DESTINATION_TELEGRAM, DESTINATION_DISCORD, DESTINATION_EMAIL):
        assert destination in DESTINATION_CLASS_OF
