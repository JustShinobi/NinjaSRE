"""Asking a person: routing, attribution, screening, expiry, and the refusal.

The refusal tests are the important ones. Article IV takes credentials out of
the agent's reach by putting them behind a proxy, and the cheapest way around
that is not an exploit — it is to ask somebody to paste one into a chat thread.
Everything else here is about the answer being attributable, redacted, and
closing the question everywhere the moment it arrives.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from capabilities.tools.system.ask_human import binding
from capabilities.tools.system.ask_human.tool import TOOL_NAME
from capabilities.tools.system.ask_human.tool import ask_human as ask_human_capability
from core.agent.handoff import (
    HandoffAnswer,
    HandoffQuestion,
    HumanHandoff,
    NoHumanAvailable,
    SecretRequestRefused,
    ask_human,
    refuse_secret_requests,
    secret_request_term,
    with_escalation,
)
from core.agent.interaction import (
    Answer,
    InteractionClosure,
    InteractionEvent,
    InteractionRegistry,
    InteractionState,
    Question,
    ScreenedText,
)
from core.capability.result import CapabilityErrorClass

pytestmark = pytest.mark.unit

AT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _RecordingSurface:
    def __init__(self, name: str) -> None:
        self._name = name
        self.presented: list[Question] = []
        self.closed_events: list[InteractionEvent] = []

    @property
    def name(self) -> str:
        return self._name

    async def present(self, interaction: object) -> None:
        self.presented.append(interaction)  # type: ignore[arg-type]

    async def closed(self, event: InteractionEvent) -> None:
        self.closed_events.append(event)


class _RedactsKeys:
    """A filter standing in for the guardrail engine."""

    def screen(self, text: str) -> ScreenedText:
        if "sk-live-" not in text:
            return ScreenedText(text=text)
        redacted = "".join(text.split("sk-live-")[0]) + "[REDACTED]"
        return ScreenedText(text=redacted, rules=("no-api-keys",), blocked=True)


def _desk(**overrides: object) -> HumanHandoff:
    registry = InteractionRegistry(run_id="run-1", clock=lambda: AT)
    defaults: dict[str, object] = {
        "registry": registry,
        "run_id": "run-1",
        "surfaces": ("slack", "console"),
        "clock": lambda: AT,
        "timeout_seconds": 0.5,
    }
    defaults.update(overrides)
    return HumanHandoff(**defaults)  # type: ignore[arg-type]


# --- the refusal (SC-005, T006, T010) ------------------------------------------


@pytest.mark.parametrize(
    "asked",
    [
        "what is the database password?",
        "can you send me the api key for the payments service",
        "paste the private key you use for the deploy",
        "tell me the bearer token so I can call the endpoint myself",
        "give me the service account key",
    ],
)
def test_a_question_asking_for_a_credential_is_named_as_one(asked: str) -> None:
    assert secret_request_term(asked)


@pytest.mark.parametrize(
    "asked",
    [
        "was the api key rotated at 11:58?",
        "does the payments service authenticate with a token or with mTLS?",
        "did anybody change the credential for the staging database this week?",
        "is the alert on the certificate expiry a known false positive?",
    ],
)
def test_a_question_that_merely_mentions_a_credential_is_allowed(asked: str) -> None:
    """Refusing these would teach the agent the subject is off limits rather
    than the disclosure."""
    assert not secret_request_term(asked)


def test_the_reason_is_read_alongside_the_question() -> None:
    """ "What is the value?" is innocent until the reason says which value."""
    assert secret_request_term("what is the value?", "I need the api key to call the endpoint")


def test_a_credential_offered_rather_than_asked_for_is_refused() -> None:
    assert secret_request_term("here is the password, is it the right one?")


def test_the_refusal_names_what_was_asked_for_and_says_what_to_ask_instead() -> None:
    with pytest.raises(SecretRequestRefused) as refused:
        refuse_secret_requests("what is the database password?")

    assert refused.value.term == "password"
    assert "credential proxy" in str(refused.value)
    assert "expired, or rotated" in str(refused.value)


async def test_the_runtime_handoff_refuses_before_the_channel_is_reached() -> None:
    """A refused question must not appear on a surface at all."""
    channel = _Answering("sk-live-abc123")

    answered = await ask_human(channel, HandoffQuestion(question="what is the api key?"))

    assert answered.refused
    assert not answered.answered
    assert channel.asked == []


async def test_the_desk_refuses_before_anything_is_raised() -> None:
    desk = _desk()

    answered = await desk.ask("paste the private key", why="I want to sign the request")

    assert answered.refused
    assert desk.registry.pending == ()


async def test_the_capability_refuses_with_permission_denied() -> None:
    """SC-005. ``PERMISSION_DENIED`` means "do not retry"; an unavailability
    would send the model looking for another channel."""
    result = await ask_human_capability("what is the database password?")

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.PERMISSION_DENIED


async def test_the_capability_reports_that_nobody_is_attached_when_unbound() -> None:
    binding.clear()

    result = await ask_human_capability("was the traffic spike expected?")

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE


async def test_the_capability_attributes_the_answer_it_returns() -> None:
    desk = _desk()
    previous = binding.bind(desk)
    try:
        asking = asyncio.ensure_future(_ask_through_capability())
        await _until(lambda: bool(desk.registry.pending))
        raised = desk.registry.pending[0]
        await desk.answer(
            raised.interaction_id, text="yes, it was the launch", principal="ada", surface="slack"
        )
        result = await asking
    finally:
        binding.restore(previous)

    assert result.succeeded
    assert result.value["answered_by"] == "ada"
    assert result.evidence[0].source == "ada"


async def _ask_through_capability() -> object:
    return await ask_human_capability("was the traffic spike expected?", why="it decides severity")


# --- routing (FR-002, T012) -----------------------------------------------------


def test_the_originating_surface_comes_first_and_escalation_follows() -> None:
    assert with_escalation("slack", ("console", "oncall")) == ("slack", "console", "oncall")


def test_a_surface_named_twice_appears_once() -> None:
    assert with_escalation("slack", ("slack", "console")) == ("slack", "console")


def test_a_run_with_no_surface_still_routes_somewhere_nameable() -> None:
    assert with_escalation("", ()) == ("unattached",)


async def test_a_question_is_shown_on_the_origin_and_the_escalation_surfaces() -> None:
    slack, oncall = _RecordingSurface("slack"), _RecordingSurface("oncall")
    closure = InteractionClosure().subscribe(slack).subscribe(oncall)
    desk = _desk(closure=closure, surfaces=with_escalation("slack", ("oncall",)))

    asking = asyncio.ensure_future(desk.ask("was the spike expected?"))
    await _until(lambda: bool(slack.presented))

    assert [surface.presented[0].text for surface in (slack, oncall)] == [
        "was the spike expected?",
        "was the spike expected?",
    ]
    asking.cancel()


# --- answering, attribution, closure (FR-004, FR-015) ---------------------------


async def test_an_answer_from_any_surface_wakes_the_waiting_loop() -> None:
    """The whole cross-surface claim: the loop does not care which surface
    answered."""
    console = _RecordingSurface("console")
    closure = InteractionClosure().subscribe(console)
    desk = _desk(closure=closure, surfaces=("console",))

    asking = asyncio.ensure_future(desk.ask("was the spike expected?"))
    await _until(lambda: bool(desk.registry.pending))
    raised = desk.registry.pending[0]
    await desk.answer(raised.interaction_id, text="yes", principal="ada", surface="console")

    answered = await asking
    assert answered.answered
    assert answered.principal == "ada"
    assert answered.answer == "yes"


async def test_answering_closes_the_question_on_every_surface() -> None:
    slack, console = _RecordingSurface("slack"), _RecordingSurface("console")
    closure = InteractionClosure().subscribe(slack).subscribe(console)
    desk = _desk(closure=closure)

    asking = asyncio.ensure_future(desk.ask("was the spike expected?"))
    await _until(lambda: bool(desk.registry.pending))
    raised = desk.registry.pending[0]
    await desk.answer(raised.interaction_id, text="yes", principal="ada", surface="console")
    await asking

    assert [event.state for event in slack.closed_events] == [InteractionState.ANSWERED]
    assert slack.closed_events[0].answered_by == "ada"


async def test_the_second_person_to_answer_is_told_who_got_there_first() -> None:
    """SC-002, through the desk rather than the registry directly."""
    desk = _desk()
    asking = asyncio.ensure_future(desk.ask("was the spike expected?"))
    await _until(lambda: bool(desk.registry.pending))
    raised = desk.registry.pending[0]

    first = await desk.answer(raised.interaction_id, text="yes", principal="ada")
    second = await desk.answer(raised.interaction_id, text="no", principal="grace")
    await asking

    assert first.won
    assert second.lost
    assert second.answered_by == "ada"


async def test_the_answer_is_attributed_in_the_stored_interaction() -> None:
    """FR-004. A conclusion resting on what somebody said is followable up."""
    desk = _desk()
    asking = asyncio.ensure_future(desk.ask("did the migration run?"))
    await _until(lambda: bool(desk.registry.pending))
    raised = desk.registry.pending[0]
    await desk.answer(raised.interaction_id, text="yes, at 11:58", principal="ada", surface="slack")
    await asking

    stored = desk.registry.get(raised.interaction_id)
    assert stored.answer is not None
    assert (stored.answer.principal, stored.answer.surface) == ("ada", "slack")
    assert stored.answer.answered_at == AT


# --- guardrail screening (FR-005, T015) -----------------------------------------


async def test_an_answer_is_redacted_before_it_reaches_the_agent() -> None:
    desk = _desk(screen=_RedactsKeys())
    asking = asyncio.ensure_future(desk.ask("how does the job authenticate?"))
    await _until(lambda: bool(desk.registry.pending))
    raised = desk.registry.pending[0]

    await desk.answer(
        raised.interaction_id, text="it uses sk-live-abc123", principal="ada", surface="slack"
    )
    answered = await asking

    assert "sk-live-" not in answered.answer
    assert answered.redacted_by == ("no-api-keys",)


async def test_the_redaction_is_what_gets_persisted_not_only_what_the_model_sees() -> None:
    """The session record outlives the turn. Redacting on the way to the model
    would leave the secret in the place it lives longest."""
    desk = _desk(screen=_RedactsKeys())
    asking = asyncio.ensure_future(desk.ask("how does the job authenticate?"))
    await _until(lambda: bool(desk.registry.pending))
    raised = desk.registry.pending[0]
    await desk.answer(raised.interaction_id, text="it uses sk-live-abc123", principal="ada")
    await asking

    stored = desk.registry.get(raised.interaction_id)
    assert stored.answer is not None
    assert "sk-live-" not in stored.answer.text


# --- expiry (FR-003, SC-003) ----------------------------------------------------


async def test_a_question_nobody_answers_expires_and_refuses_to_guess() -> None:
    console = _RecordingSurface("console")
    closure = InteractionClosure().subscribe(console)
    desk = _desk(closure=closure, surfaces=("console",), timeout_seconds=0.01)

    answered = await desk.ask("was the spike expected?")

    assert not answered.answered
    assert not answered.usable
    assert "unanswered" in answered.answer
    assert [event.state for event in console.closed_events] == [InteractionState.EXPIRED]


async def test_an_expired_question_can_no_longer_be_answered() -> None:
    desk = _desk(timeout_seconds=0.01)
    await desk.ask("was the spike expected?")
    raised = desk.registry.all_interactions[0]

    late = await desk.answer(raised.interaction_id, text="yes", principal="ada")

    assert late.lost
    assert "expired" in late.reason


# --- the direct channel path ----------------------------------------------------


class _Answering:
    def __init__(self, answer: str, principal: str = "") -> None:
        self.answer = answer
        self.principal = principal
        self.asked: list[HandoffQuestion] = []

    async def ask(self, question: HandoffQuestion) -> HandoffAnswer:
        self.asked.append(question)
        return HandoffAnswer(answer=self.answer, principal=self.principal, surface="cli")


async def test_a_channel_answer_goes_through_the_registry_like_any_other() -> None:
    desk = _desk(channel=_Answering("yes, the launch", principal="ada"))

    answered = await desk.ask("was the spike expected?")

    assert answered.answered
    assert answered.principal == "ada"
    assert desk.registry.all_interactions[0].state is InteractionState.ANSWERED


async def test_a_surface_answer_beats_a_channel_that_is_still_thinking() -> None:
    class _Slow:
        async def ask(self, question: HandoffQuestion) -> HandoffAnswer:
            await asyncio.sleep(5)
            return HandoffAnswer(answer="too late", principal="grace")

    desk = _desk(channel=_Slow())
    asking = asyncio.ensure_future(desk.ask("was the spike expected?"))
    await _until(lambda: bool(desk.registry.pending))
    raised = desk.registry.pending[0]
    await desk.answer(raised.interaction_id, text="yes", principal="ada", surface="slack")

    answered = await asking
    assert answered.principal == "ada"


async def test_the_default_channel_says_nobody_is_attached_without_waiting() -> None:
    desk = _desk(channel=NoHumanAvailable(), timeout_seconds=30.0)

    answered = await desk.ask("was the spike expected?")

    assert not answered.answered
    assert "No person is attached" in answered.answer


def test_the_declared_capability_is_never_run_alongside_another_question() -> None:
    registered = getattr(ask_human_capability, "__ninjasre_capability__", None)
    assert registered is not None
    assert registered.metadata.parallel_safe is False
    assert registered.metadata.name == TOOL_NAME


async def _until(condition: object, *, tries: int = 200) -> None:
    """Yield to the loop until ``condition`` holds, so no test sleeps a fixed time."""
    for _ in range(tries):
        if condition():  # type: ignore[operator]
            return
        await asyncio.sleep(0)
    raise AssertionError("the condition never became true")


def test_an_answer_carries_its_own_usability() -> None:
    assert Answer(text="yes").usable
    assert not Answer(text="", answered=True).usable
    assert not Answer(text="anything", answered=False).usable
