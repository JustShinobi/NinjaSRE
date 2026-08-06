"""Approvals inherit the four properties, rather than reimplementing them.

The claim feature 018 makes is that a queued change and a question the agent
asked are one situation, so cross-surface closure, persistence, concurrency
resolution, and attention state are each written once. This file is what turns
that from a design statement into something CI enforces: every test here drives
an *approval* through machinery that was written for questions, and none of them
would pass if the two had stayed separate.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.security import PENDING_CHANGE_EXPIRY_HOURS
from core.agent.interaction import (
    Answer,
    ApprovalInteraction,
    AttentionState,
    InteractionClosure,
    InteractionEvent,
    InteractionKind,
    InteractionRegistry,
    InteractionState,
    attention_over,
    from_records,
    question,
    restore_registry,
    to_records,
)
from platform.approvals.closure import ClosurePublisher, DecisionEvent
from platform.approvals.interaction import event_of, interaction_of
from platform.approvals.models import (
    ChangeState,
    ChangeTarget,
    ChangeType,
    Decision,
    PendingChange,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _RecordingSubscriber:
    """An approvals surface, in the vocabulary feature 015 gave it."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.closed_events: list[DecisionEvent] = []

    @property
    def name(self) -> str:
        return self._name

    async def closed(self, event: DecisionEvent) -> None:
        self.closed_events.append(event)


class _BrokenSubscriber(_RecordingSubscriber):
    async def closed(self, event: DecisionEvent) -> None:
        raise ConnectionError(f"{self.name} is unreachable")


def _change(change_id: str = "c1", **overrides: object) -> PendingChange:
    change = PendingChange.queued(
        change_id=change_id,
        change_type=ChangeType.REMEDIATION,
        target=ChangeTarget(identifier="checkout", node_id="payments"),
        proposed={"replicas": 6},
        current={"replicas": 3},
        requester="ada",
        rationale="the pods are saturated",
        at=AT,
    )
    return change if not overrides else _replaced(change, overrides)


def _replaced(change: PendingChange, overrides: dict[str, object]) -> PendingChange:
    from dataclasses import replace

    return replace(change, **overrides)  # type: ignore[arg-type]


# --- the conversion --------------------------------------------------------------


def test_a_queued_change_is_an_interaction() -> None:
    converted = interaction_of(_change())

    assert isinstance(converted, ApprovalInteraction)
    assert converted.kind is InteractionKind.APPROVAL
    assert converted.state is InteractionState.PENDING
    assert converted.expires_at == AT + timedelta(hours=PENDING_CHANGE_EXPIRY_HOURS)


def test_a_conflicted_change_is_still_somebody_being_waited_on() -> None:
    """Conflicted is undecided. A queue that hid it would be a queue where the
    conflicted change waited until it expired."""
    converted = interaction_of(_change().with_state(ChangeState.CONFLICTED))

    assert converted.state is InteractionState.PENDING
    assert converted.is_open


def test_a_rejection_is_an_answer_rather_than_a_failure_to_answer() -> None:
    """Surfaces have to stop showing a button for a rejected change exactly as
    much as for an approved one."""
    rejected = _change().decided(
        Decision(approved=False, decided_by="grace", decided_at=AT, reason="too risky mid-incident")
    )

    converted = interaction_of(rejected)

    assert converted.state is InteractionState.ANSWERED
    assert converted.answer is not None
    assert converted.answer.principal == "grace"
    assert "too risky" in converted.answer.text


def test_an_expired_change_expires_rather_than_being_answered() -> None:
    converted = interaction_of(_change().with_state(ChangeState.EXPIRED))

    assert converted.state is InteractionState.EXPIRED


def test_the_interaction_carries_what_a_reviewer_is_shown() -> None:
    converted = interaction_of(
        _change(),
        blast_radius="6 pods in payments",
        rollback_plan="scale back to three replicas",
    )

    assert converted.blast_radius == "6 pods in payments"
    assert converted.rollback_plan == "scale back to three replicas"
    assert "checkout" in converted.describe()


# --- inherited: cross-surface closure (T038) --------------------------------------


async def test_a_decision_closes_every_surface_through_the_shared_publisher() -> None:
    slack, console = _RecordingSubscriber("slack"), _RecordingSubscriber("console")
    publisher = ClosurePublisher().subscribe(slack).subscribe(console)
    approved = _change().decided(Decision(approved=True, decided_by="grace", decided_at=AT))

    told = await publisher.publish(DecisionEvent.of(approved, at=AT))

    assert set(told) == {"slack", "console"}
    assert [event.state for event in slack.closed_events] == [ChangeState.APPROVED]


async def test_a_decision_is_published_once_however_often_it_is_retried() -> None:
    slack = _RecordingSubscriber("slack")
    publisher = ClosurePublisher().subscribe(slack)
    event = DecisionEvent.of(_change(), at=AT)

    first = await publisher.publish(event)
    second = await publisher.publish(event)

    assert first == ("slack",)
    assert second == ()
    assert len(slack.closed_events) == 1
    assert publisher.has_published("c1")


async def test_one_broken_surface_does_not_leave_the_others_showing_a_button() -> None:
    console = _RecordingSubscriber("console")
    publisher = ClosurePublisher().subscribe(_BrokenSubscriber("slack")).subscribe(console)

    told = await publisher.publish(DecisionEvent.of(_change(), at=AT))

    assert told == ("console",)
    assert len(console.closed_events) == 1


async def test_an_expiry_sweep_closes_every_change_it_lapsed() -> None:
    slack = _RecordingSubscriber("slack")
    publisher = ClosurePublisher().subscribe(slack)
    lapsed = [
        DecisionEvent.of(_change("c1").with_state(ChangeState.EXPIRED), at=AT),
        DecisionEvent.of(_change("c2").with_state(ChangeState.EXPIRED), at=AT),
    ]

    await publisher.publish_all(lapsed)

    assert [event.change_id for event in slack.closed_events] == ["c1", "c2"]


async def test_a_question_and_an_approval_close_through_the_same_publisher() -> None:
    """The unification, stated as a test: one surface, one closure, both kinds."""

    class _Both:
        def __init__(self) -> None:
            self.seen: list[InteractionEvent] = []

        @property
        def name(self) -> str:
            return "slack"

        async def present(self, interaction: object) -> None:
            return None

        async def closed(self, event: InteractionEvent) -> None:
            self.seen.append(event)

    surface = _Both()
    closure = InteractionClosure().subscribe(surface)

    await closure.publish(
        InteractionEvent.of(
            question(
                interaction_id="q1",
                run_id="run-1",
                text="was the spike expected?",
                surfaces=("slack",),
                at=AT,
            ),
            at=AT,
        )
    )
    await closure.publish(event_of(_change(), at=AT, surfaces=("slack",)))

    assert [event.kind for event in surface.seen] == [
        InteractionKind.QUESTION,
        InteractionKind.APPROVAL,
    ]


# --- inherited: persistence -------------------------------------------------------


def test_a_pending_approval_survives_a_restart() -> None:
    records = json.loads(json.dumps(to_records((interaction_of(_change()),))))
    restored = restore_registry(from_records(records), run_id="c1", now=lambda: AT)

    held = restored.get("c1")
    assert held.state is InteractionState.PENDING
    assert isinstance(held, ApprovalInteraction)


def test_an_approval_whose_window_closed_comes_back_expired() -> None:
    much_later = AT + timedelta(hours=PENDING_CHANGE_EXPIRY_HOURS * 2)

    restored = restore_registry(
        from_records(to_records((interaction_of(_change()),))), run_id="c1", now=lambda: much_later
    )

    assert restored.get("c1").state is InteractionState.EXPIRED


# --- inherited: concurrency resolution --------------------------------------------


def test_two_reviewers_deciding_at_once_resolve_to_the_first() -> None:
    registry = InteractionRegistry(run_id="c1", clock=lambda: AT)
    registry.raise_interaction(interaction_of(_change()))

    first = registry.resolve("c1", Answer(text="approved", principal="grace"))
    second = registry.resolve("c1", Answer(text="rejected", principal="ada"))

    assert first.won
    assert second.lost
    assert second.answered_by == "grace"


# --- inherited: attention state ----------------------------------------------------


def test_a_run_blocked_on_an_approval_is_distinguishable_in_a_listing() -> None:
    attention = attention_over((interaction_of(_change()),))

    assert attention.state is AttentionState.WAITING_ON_APPROVAL
    assert attention.approvals == 1
    assert attention.waiting_since == AT


def test_a_decided_approval_stops_asking_for_attention() -> None:
    decided = _change().decided(Decision(approved=True, decided_by="grace", decided_at=AT))

    assert not attention_over((interaction_of(decided),)).needs_attention


def test_a_question_and_an_approval_on_one_run_report_both() -> None:
    blocked = attention_over(
        (
            question(interaction_id="q1", run_id="run-1", text="was it expected?", at=AT),
            interaction_of(_change()),
        )
    )

    assert blocked.state is AttentionState.WAITING_ON_BOTH
    assert (blocked.questions, blocked.approvals) == (1, 1)
