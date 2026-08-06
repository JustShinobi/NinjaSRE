"""The four properties that only exist because questions and approvals are one type.

Each test here is written against ``Interaction`` rather than against a question
or an approval, and every one of them is a property that would have been
implemented twice — and therefore differently — if the two had stayed separate:

- answering on one surface closes every other one (SC-001);
- two people answering at once resolve to one, with the other told (SC-002);
- a pending interaction survives a restart, answerable or clearly expired
  (SC-007);
- a run listing can say which runs are waiting on somebody.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.investigation import (
    INTERACTION_CLOSURE_BUDGET_SECONDS,
    INTERACTION_EXPIRY_SECONDS,
)
from core.agent.interaction import (
    Answer,
    ApprovalInteraction,
    AttentionState,
    Interaction,
    InteractionClosure,
    InteractionEvent,
    InteractionKind,
    InteractionRegistry,
    InteractionState,
    InteractionSurface,
    Question,
    UnknownInteraction,
    attention_over,
    from_records,
    question,
    restore_registry,
    to_records,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _RecordingSurface:
    """A surface that remembers what it was shown and what it was told to close."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.presented: list[Interaction] = []
        self.closed_events: list[InteractionEvent] = []

    @property
    def name(self) -> str:
        return self._name

    async def present(self, interaction: Interaction) -> None:
        self.presented.append(interaction)

    async def closed(self, event: InteractionEvent) -> None:
        self.closed_events.append(event)


class _BrokenSurface(_RecordingSurface):
    """A surface that is down when the closure arrives."""

    async def closed(self, event: InteractionEvent) -> None:
        raise ConnectionError(f"{self.name} is unreachable")


def _question(interaction_id: str = "i1", **overrides: object) -> Question:
    defaults: dict[str, object] = {
        "interaction_id": interaction_id,
        "run_id": "run-1",
        "text": "was the traffic spike the marketing launch?",
        "reason": "it decides whether this is an incident at all",
        "options": ("yes", "no", "not sure"),
        "surfaces": ("slack", "console"),
        "at": AT,
    }
    defaults.update(overrides)
    return question(**defaults)  # type: ignore[arg-type]


def _approval(interaction_id: str = "a1") -> ApprovalInteraction:
    return ApprovalInteraction(
        interaction_id=interaction_id,
        run_id="run-1",
        raised_at=AT,
        expires_at=AT + timedelta(seconds=INTERACTION_EXPIRY_SECONDS),
        surfaces=("slack", "console"),
        summary="restart the checkout deployment",
        action="kubernetes.restart_deployment",
        blast_radius="6 pods in payments",
        rollback_plan="scale back to the previous replica set",
    )


# --- the supertype -------------------------------------------------------------


def test_a_question_and_an_approval_are_the_same_type() -> None:
    """The whole point. A surface holding one holds the other."""
    assert isinstance(_question(), Interaction)
    assert isinstance(_approval(), Interaction)


def test_an_interaction_that_is_already_expired_when_raised_is_refused() -> None:
    with pytest.raises(ValueError, match="already closed"):
        Question(
            interaction_id="i1",
            run_id="run-1",
            raised_at=AT,
            expires_at=AT,
            text="anything",
        )


def test_a_question_has_to_carry_a_question() -> None:
    with pytest.raises(ValueError, match="question"):
        _question(text="   ")


# --- cross-surface closure (SC-001, T003) --------------------------------------


async def test_answering_on_one_surface_closes_it_on_every_other() -> None:
    """SC-001. The stale button in the Slack thread is the failure this prevents."""
    slack, console = _RecordingSurface("slack"), _RecordingSurface("console")
    closure = InteractionClosure().subscribe(slack).subscribe(console)
    registry = InteractionRegistry(run_id="run-1")
    raised = registry.raise_interaction(_question())

    await closure.present(raised)
    resolution = registry.resolve("i1", Answer(text="yes", principal="ada", surface="console"))
    propagation = await closure.publish(InteractionEvent.of(resolution.interaction, at=AT))

    assert resolution.won
    assert set(propagation.closed) == {"slack", "console"}
    assert [event.state for event in slack.closed_events] == [InteractionState.ANSWERED]
    assert slack.closed_events[0].answered_by == "ada"


async def test_closure_reaches_every_surface_within_the_propagation_budget() -> None:
    """SC-001's second half: it closes everywhere, and it does so promptly."""
    elapsed = iter([0.0, INTERACTION_CLOSURE_BUDGET_SECONDS / 2])
    closure = InteractionClosure(clock=lambda: next(elapsed))
    closure.subscribe(_RecordingSurface("slack")).subscribe(_RecordingSurface("console"))

    propagation = await closure.publish(InteractionEvent.of(_question(), at=AT))

    assert propagation.within_budget
    assert propagation.reached_everybody


async def test_a_surface_that_is_down_does_not_leave_the_others_showing_a_button() -> None:
    slack = _BrokenSurface("slack")
    console = _RecordingSurface("console")
    closure = InteractionClosure().subscribe(slack).subscribe(console)

    propagation = await closure.publish(InteractionEvent.of(_question(), at=AT))

    assert propagation.closed == ("console",)
    assert propagation.failed == ("slack",)
    assert not propagation.reached_everybody


async def test_a_closure_is_published_once_however_often_it_is_retried() -> None:
    """A retried decision path must not put a second announcement in a channel."""
    slack = _RecordingSurface("slack")
    closure = InteractionClosure().subscribe(slack)
    event = InteractionEvent.of(_question(surfaces=("slack",)), at=AT)

    first = await closure.publish(event)
    second = await closure.publish(event)

    assert first.closed == ("slack",)
    assert second.duplicate
    assert len(slack.closed_events) == 1


async def test_an_interaction_travels_only_to_the_surfaces_it_names() -> None:
    """Article X. A question routed to Slack does not appear in Discord."""
    slack, discord = _RecordingSurface("slack"), _RecordingSurface("discord")
    closure = InteractionClosure().subscribe(slack).subscribe(discord)

    await closure.present(_question(surfaces=("slack",)))

    assert len(slack.presented) == 1
    assert discord.presented == []


async def test_a_surface_that_has_gone_away_does_not_stop_the_rest_closing() -> None:
    """T021. The requester left the channel; the escalation surface still hears."""
    escalation = _RecordingSurface("oncall-channel")
    closure = InteractionClosure().subscribe(escalation)
    raised = _question(surfaces=("archived-thread", "oncall-channel"))

    propagation = await closure.publish(InteractionEvent.of(raised, at=AT))

    assert propagation.closed == ("oncall-channel",)
    assert propagation.reached_everybody


# --- concurrency (SC-002, T004) ------------------------------------------------


def test_two_people_answering_at_once_resolve_to_the_first() -> None:
    """SC-002. Deterministic, and the loser is told who won rather than only that
    they lost."""
    registry = InteractionRegistry(run_id="run-1")
    registry.raise_interaction(_question())

    first = registry.resolve("i1", Answer(text="yes", principal="ada", surface="console"))
    second = registry.resolve("i1", Answer(text="no", principal="grace", surface="slack"))

    assert first.won
    assert second.lost
    assert second.answered_by == "ada"
    assert "ada" in second.reason
    assert registry.get("i1").answer is not None
    assert registry.get("i1").answer.text == "yes"  # type: ignore[union-attr]


def test_an_answer_arriving_after_the_investigation_concluded_is_told_so() -> None:
    registry = InteractionRegistry(run_id="run-1")
    registry.raise_interaction(_question())
    registry.supersede_open(reason="the run concluded")

    late = registry.resolve("i1", Answer(text="yes", principal="ada"))

    assert late.lost
    assert "no longer applies" in late.reason


def test_answering_something_that_was_never_asked_is_a_different_failure() -> None:
    """A wiring problem and a race must not report the same thing."""
    with pytest.raises(UnknownInteraction):
        InteractionRegistry(run_id="run-1").resolve("nope", Answer(text="yes", principal="ada"))


def test_raising_the_same_identifier_twice_is_refused() -> None:
    registry = InteractionRegistry(run_id="run-1")
    registry.raise_interaction(_question())

    with pytest.raises(ValueError, match="already raised"):
        registry.raise_interaction(_question())


def test_the_registry_stamps_an_answer_that_carries_no_time() -> None:
    registry = InteractionRegistry(run_id="run-1", clock=lambda: AT)
    registry.raise_interaction(_question())

    resolved = registry.resolve("i1", Answer(text="yes", principal="ada"))

    assert resolved.interaction.answer is not None
    assert resolved.interaction.answer.answered_at == AT  # type: ignore[union-attr]


# --- persistence (SC-007, T005) ------------------------------------------------


def test_a_pending_question_survives_a_restart_and_is_still_answerable() -> None:
    """SC-007. The run comes back knowing what it stopped for."""
    registry = InteractionRegistry(run_id="run-1", clock=lambda: AT)
    registry.raise_interaction(_question())

    records = json.loads(json.dumps(to_records(registry.pending)))
    resumed = restore_registry(from_records(records), run_id="run-1", now=lambda: AT)

    restored = resumed.get("i1")
    assert restored.state is InteractionState.PENDING
    assert isinstance(restored, Question)
    assert restored.options == ("yes", "no", "not sure")
    assert resumed.resolve("i1", Answer(text="yes", principal="ada")).won


def test_a_question_whose_window_closed_during_the_outage_comes_back_expired() -> None:
    """SC-007's other half. Clearly expired beats silently answerable."""
    registry = InteractionRegistry(run_id="run-1", clock=lambda: AT)
    registry.raise_interaction(_question())
    much_later = AT + timedelta(seconds=INTERACTION_EXPIRY_SECONDS * 2)

    resumed = restore_registry(
        from_records(to_records(registry.pending)), run_id="run-1", now=lambda: much_later
    )

    assert resumed.get("i1").state is InteractionState.EXPIRED
    assert resumed.resolve("i1", Answer(text="yes", principal="ada")).lost


def test_an_approval_round_trips_with_everything_a_reviewer_is_shown() -> None:
    """The unification is only real if the approval survives the same journey."""
    restored = from_records(to_records((_approval(),)))[0]

    assert isinstance(restored, ApprovalInteraction)
    assert restored.kind is InteractionKind.APPROVAL
    assert restored.blast_radius == "6 pods in payments"
    assert restored.rollback_plan == "scale back to the previous replica set"


def test_an_unreadable_record_is_dropped_rather_than_failing_the_resumption() -> None:
    """A session that will not load is an investigation somebody restarts from
    the alert."""
    good = to_records((_question(),))
    restored = from_records([*good, {"interaction_id": "broken"}])

    assert [held.interaction_id for held in restored] == ["i1"]


def test_an_answered_interaction_round_trips_with_its_attribution() -> None:
    registry = InteractionRegistry(run_id="run-1", clock=lambda: AT)
    registry.raise_interaction(_question())
    registry.resolve("i1", Answer(text="yes", principal="ada", surface="console"))

    restored = from_records(to_records(registry.all_interactions))[0]

    assert restored.state is InteractionState.ANSWERED
    assert restored.answer is not None
    assert restored.answer.principal == "ada"  # type: ignore[union-attr]
    assert restored.answer.surface == "console"  # type: ignore[union-attr]


# --- attention (T033) ----------------------------------------------------------


def test_a_run_waiting_on_nothing_needs_no_attention() -> None:
    assert not attention_over(()).needs_attention


def test_a_run_waiting_on_a_question_is_distinguishable_in_a_listing() -> None:
    attention = attention_over((_question(),))

    assert attention.state is AttentionState.WAITING_ON_QUESTION
    assert attention.questions == 1
    assert attention.waiting_since == AT
    assert "traffic spike" in attention.summary


def test_a_run_waiting_on_both_kinds_says_so() -> None:
    attention = attention_over((_question(), _approval()))

    assert attention.state is AttentionState.WAITING_ON_BOTH
    assert (attention.questions, attention.approvals) == (1, 1)


def test_attention_is_measured_from_the_longest_waiting_interaction() -> None:
    """A queue sorted by how long it has been ignored is what stops the question
    nobody noticed from staying unanswered."""
    older = _question("i1", at=AT)
    newer = _question("i2", at=AT + timedelta(minutes=5))

    assert attention_over((newer, older)).waiting_since == AT


def test_an_answered_interaction_stops_asking_for_attention() -> None:
    registry = InteractionRegistry(run_id="run-1")
    registry.raise_interaction(_question())
    registry.resolve("i1", Answer(text="yes", principal="ada"))

    assert not attention_over(registry.all_interactions).needs_attention


def test_attention_reaches_a_run_listing_as_metadata() -> None:
    metadata = attention_over((_approval(),)).to_metadata()

    assert metadata["attention"] == AttentionState.WAITING_ON_APPROVAL.value
    assert metadata["attention_since"] == AT.isoformat()


# --- expiry --------------------------------------------------------------------


def test_expiry_closes_the_window_and_reports_what_lapsed() -> None:
    registry = InteractionRegistry(run_id="run-1", clock=lambda: AT)
    registry.raise_interaction(_question())

    lapsed = registry.expire_due(AT + timedelta(seconds=INTERACTION_EXPIRY_SECONDS + 1))

    assert [held.interaction_id for held in lapsed] == ["i1"]
    assert registry.pending == ()


def test_the_surface_port_is_structural() -> None:
    assert isinstance(_RecordingSurface("slack"), InteractionSurface)
