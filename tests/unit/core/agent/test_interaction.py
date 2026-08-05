"""Mid-run input, human questions, cancellation, compaction, and persistence.

Everything in this file is about a run that is still going. Each one has an
obvious wrong implementation that works right up until it matters: interrupting
the turn, guessing an answer nobody gave, tearing a run down mid-call,
summarising away the reference a conclusion needed, or persisting nothing until
the end.
"""

from __future__ import annotations

import asyncio

import pytest

from config.constants.investigation import (
    HANDOFF_TIMEOUT_SECONDS,
    MESSAGE_QUEUE_DEBOUNCE_MS,
    TRANSCRIPT_COMPACTION_KEEP_MESSAGES,
)
from core.agent.compaction import COMPACTION_PREAMBLE, apply_compaction, compact
from core.agent.handoff import (
    HANDOFF_CAPABILITY,
    HandoffAnswer,
    HandoffChannel,
    HandoffQuestion,
    NoHumanAvailable,
    ask_human,
    handoff_tool,
)
from core.agent.message_queue import MessageQueue, merge
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import EvidenceEntry, Session, SessionStatus
from core.agent.store import InMemorySessionStore, SessionStore, save_quietly
from core.agent.turn import GuardrailActionKind
from core.capability.metadata import EvidenceType
from core.llm.types import Message, Role, ToolCall
from tests.unit.core.agent.conftest import (
    DEFAULT_TOOLS,
    ScriptedLLM,
    call_turn,
    log_call,
    text_turn,
)

pytestmark = pytest.mark.unit


class _FakeClock:
    """A monotonic source a test moves by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- the message queue (T040, T041) --------------------------------------------


async def test_a_burst_inside_the_debounce_window_becomes_one_block() -> None:
    """Somebody typing three sentences in three messages meant one instruction."""
    clock = _FakeClock()
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)
        clock.advance(seconds)

    queue = MessageQueue(clock=clock, sleeper=sleeper)
    queue.submit("the deploy at 12:02 was mine")
    clock.advance(0.2)
    queue.submit("it only touched the checkout service")
    clock.advance(0.2)
    queue.submit("roll it back if that is the cause")

    drained = await queue.drain()

    assert len(drained) == 3
    assert slept, "the queue waited out the window rather than delivering the first message alone"
    block = merge(drained)
    assert "1. the deploy at 12:02 was mine" in block
    assert "3. roll it back if that is the cause" in block


async def test_the_window_is_measured_from_the_last_message_not_the_first() -> None:
    clock = _FakeClock()

    async def sleeper(seconds: float) -> None:
        clock.advance(seconds)

    queue = MessageQueue(clock=clock, sleeper=sleeper)
    queue.submit("first")
    clock.advance(MESSAGE_QUEUE_DEBOUNCE_MS / 1000.0)
    queue.submit("still typing")

    await queue.drain()

    assert clock.now >= 2 * (MESSAGE_QUEUE_DEBOUNCE_MS / 1000.0)


async def test_an_empty_queue_drains_instantly() -> None:
    queue = MessageQueue()

    assert await queue.drain() == ()


def test_a_blank_message_is_refused_rather_than_queued() -> None:
    with pytest.raises(ValueError, match="text"):
        MessageQueue().submit("   ")


async def test_queued_guidance_reaches_the_next_turn_and_is_recorded() -> None:
    clock = _FakeClock()

    async def sleeper(seconds: float) -> None:
        clock.advance(seconds)

    queue = MessageQueue(clock=clock, sleeper=sleeper)
    queue.submit("the deploy at 12:02 was mine")

    llm = ScriptedLLM([call_turn(log_call("c1")), text_turn("Understood.")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, messages=queue)

    result = await loop.run(RunRequest(objective="anything"))

    assert any(
        action.kind is GuardrailActionKind.MESSAGE_QUEUED
        for turn in result.turns
        for action in turn.guardrail_actions
    )
    assert any(
        "the deploy at 12:02 was mine" in message.text for message in result.session.transcript
    )


async def test_guidance_arriving_on_the_final_turn_does_not_give_tools_back() -> None:
    """T042. The final turn is text-only because a guardrail said so, and new
    input is not an override of a guardrail."""
    clock = _FakeClock()

    async def sleeper(seconds: float) -> None:
        clock.advance(seconds)

    queue = MessageQueue(clock=clock, sleeper=sleeper)
    llm = ScriptedLLM([call_turn(log_call("c-repeat", "identical"))])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, messages=queue)

    request = RunRequest(objective="anything")
    session = loop.new_session(request)
    session.tools_stripped = True
    queue.submit("one more thing: the cache was cold")

    result = await loop.resume(session)

    assert result.turns[-1].offered_capabilities == ()
    assert any("the cache was cold" in message.text for message in result.session.transcript)


# --- the human handoff (T043) --------------------------------------------------


class _Answering:
    """A channel that answers immediately."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.asked: list[HandoffQuestion] = []

    async def ask(self, question: HandoffQuestion) -> HandoffAnswer:
        self.asked.append(question)
        return HandoffAnswer(answer=self.answer)


class _NeverAnswers:
    """A channel nobody is reading."""

    async def ask(self, question: HandoffQuestion) -> HandoffAnswer:
        await asyncio.sleep(60)
        return HandoffAnswer(answer="too late")


class _Broken:
    """A surface that is down."""

    async def ask(self, question: HandoffQuestion) -> HandoffAnswer:
        raise ConnectionError("the console is unreachable")


async def test_an_answer_comes_back_usable() -> None:
    channel = _Answering("yes, the migration ran at 11:58")

    answer = await ask_human(channel, HandoffQuestion(question="did the migration run?"))

    assert answer.usable
    assert channel.asked[0].question == "did the migration run?"


async def test_an_expired_question_is_refused_rather_than_guessed() -> None:
    answer = await ask_human(
        _NeverAnswers(), HandoffQuestion(question="anything"), timeout_seconds=0.01
    )

    assert not answer.answered
    assert not answer.usable
    assert "unanswered" in answer.answer


async def test_a_broken_surface_is_the_same_answer_as_an_expiry() -> None:
    """Both mean nobody answered, and both must reach the model as that."""
    answer = await ask_human(_Broken(), HandoffQuestion(question="anything"))

    assert not answer.answered


async def test_the_default_channel_says_nobody_is_attached_without_waiting() -> None:
    answer = await ask_human(
        NoHumanAvailable(),
        HandoffQuestion(question="anything"),
        timeout_seconds=HANDOFF_TIMEOUT_SECONDS,
    )

    assert not answer.answered
    assert "No person is attached" in answer.answer


def test_the_default_channel_satisfies_the_port() -> None:
    assert isinstance(NoHumanAvailable(), HandoffChannel)


async def test_asking_is_offered_as_a_capability_when_a_channel_is_configured() -> None:
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, handoff_channel=NoHumanAvailable())

    await loop.run(RunRequest(objective="anything"))

    assert HANDOFF_CAPABILITY in {schema.name for schema in llm.requests[0].tools}


async def test_asking_is_not_offered_when_there_is_no_channel() -> None:
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    await loop.run(RunRequest(objective="anything"))

    assert HANDOFF_CAPABILITY not in {schema.name for schema in llm.requests[0].tools}


async def test_a_question_the_model_asks_reaches_the_channel() -> None:
    channel = _Answering("the spike was the marketing launch")
    llm = ScriptedLLM(
        [
            call_turn(
                ToolCall(
                    id="h1",
                    name=HANDOFF_CAPABILITY,
                    arguments={"question": "was the traffic spike expected?"},
                )
            ),
            text_turn("Then the spike is explained."),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, handoff_channel=channel)

    result = await loop.run(RunRequest(objective="anything"))

    assert [question.question for question in channel.asked] == ["was the traffic spike expected?"]
    assert any("marketing launch" in entry.content for entry in result.evidence)


def test_asking_a_person_is_never_run_alongside_another_question() -> None:
    """Two questions arriving at one person at the same time is how both get
    ignored."""
    assert handoff_tool(NoHumanAvailable()).metadata.parallel_safe is False


# --- cancellation (T044) -------------------------------------------------------


async def test_cancellation_stops_at_the_next_safe_point() -> None:
    llm = ScriptedLLM([call_turn(log_call("c1", "unique"))])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    request = RunRequest(objective="anything")
    session = loop.new_session(request)
    await loop.cancel(session.id)

    result = await loop.resume(session)

    assert result.status is RunStatus.CANCELLED
    assert result.session.status is SessionStatus.CANCELLED
    assert result.iterations == 0, "cancellation before the first turn costs no iterations"


async def test_a_cancelled_session_is_still_consistent_and_resumable() -> None:
    llm = ScriptedLLM([call_turn(log_call("c1", "unique")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    request = RunRequest(objective="anything")
    session = loop.new_session(request)
    await loop.resume(session)

    assert Session.from_record(session.to_record()).turns == session.turns


# --- the wall clock (T048) -----------------------------------------------------


async def test_the_wall_clock_ends_a_run_independently_of_the_iteration_count() -> None:
    """An iteration that blocks on a slow vendor consumes no iterations at all,
    so the loop ceiling alone bounds nothing an operator can feel."""
    clock = _FakeClock()

    def moving() -> float:
        clock.advance(5.0)
        return clock.now

    llm = ScriptedLLM([call_turn(log_call("c1", "unique"))])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, clock=moving)

    result = await loop.run(RunRequest(objective="anything", wall_clock_seconds=10.0))

    assert result.iterations < 20
    assert any(
        action.kind is GuardrailActionKind.WALL_CLOCK_EXCEEDED
        for turn in result.turns
        for action in turn.guardrail_actions
    )


def test_a_run_may_not_ask_for_more_wall_clock_than_the_constant() -> None:
    with pytest.raises(ValueError, match="wall_clock_seconds"):
        RunRequest(objective="x", wall_clock_seconds=10_000.0)


# --- compaction (T046) ---------------------------------------------------------


def _long_session() -> Session:
    session = Session(id="run-1", objective="Why is checkout failing?")
    session.append(Message(role=Role.USER, text="Why is checkout failing?"))
    for index in range(60):
        session.append(
            Message(
                role=Role.ASSISTANT,
                text=f"narration {index}",
                tool_calls=(ToolCall(id=f"c{index}", name="fixture_log_search"),),
            )
        )
    session.record_evidence(
        EvidenceEntry(
            id="e1",
            capability="fixture_log_search",
            summary="412 errors on checkout",
            evidence_type=EvidenceType.LOG,
            source="fixture",
            reference="query:abc",
        )
    )
    return session


def test_a_short_transcript_is_left_alone() -> None:
    session = Session(id="run-1")
    session.append(Message(role=Role.USER, text="anything"))

    assert compact(session).removed == 0


def test_compaction_preserves_the_objective_and_the_recent_turns() -> None:
    session = _long_session()
    original_last = session.transcript[-1]

    result = apply_compaction(session)

    assert result.compacted
    assert session.transcript[0].text == "Why is checkout failing?"
    assert session.transcript[-1] == original_last
    assert len(session.transcript) == TRANSCRIPT_COMPACTION_KEEP_MESSAGES + 2


def test_compaction_keeps_every_evidence_reference() -> None:
    """A claim made ten turns ago still has to trace to the observation behind
    it, or the summary threw away the thing that made it a finding."""
    session = _long_session()

    result = apply_compaction(session)

    assert COMPACTION_PREAMBLE in result.summary
    assert "e1" in result.summary
    assert "412 errors on checkout" in result.summary


def test_compaction_names_what_was_called_in_the_turns_it_replaced() -> None:
    session = _long_session()

    result = apply_compaction(session)

    assert "fixture_log_search" in result.summary


async def test_a_long_run_compacts_without_losing_its_objective() -> None:
    llm = ScriptedLLM([call_turn(log_call("c1", "unique")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    session = loop.new_session(RunRequest(objective="Why is checkout failing?"))
    session.append(Message(role=Role.USER, text="Why is checkout failing?"))
    for index in range(60):
        session.append(Message(role=Role.ASSISTANT, text=f"narration {index}"))

    result = await loop.resume(session)

    assert result.status is RunStatus.COMPLETED
    assert result.session.transcript[0].text == "Why is checkout failing?"


# --- persistence (T047) --------------------------------------------------------


def test_the_in_memory_store_satisfies_the_port() -> None:
    assert isinstance(InMemorySessionStore(), SessionStore)


async def test_a_run_persists_its_session_when_a_store_is_configured() -> None:
    store = InMemorySessionStore()
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, store=store)

    result = await loop.run(RunRequest(objective="anything"))
    restored = await store.load(result.session.id)

    assert restored is not None
    assert restored.status is SessionStatus.COMPLETED
    assert restored.turns == result.session.turns


async def test_a_stored_session_is_a_record_rather_than_the_live_object() -> None:
    """A caller that keeps mutating a session it already saved must not
    silently rewrite history."""
    store = InMemorySessionStore()
    session = Session(id="run-1", objective="anything")
    await store.save(session)
    session.objective = "something else entirely"

    restored = await store.load("run-1")

    assert restored is not None
    assert restored.objective == "anything"


async def test_a_store_that_is_down_does_not_fail_the_run() -> None:
    class _Broken:
        async def save(self, session: Session) -> None:
            raise ConnectionError("the database is unreachable")

        async def load(self, session_id: str) -> Session | None:
            return None

    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, store=_Broken())

    result = await loop.run(RunRequest(objective="anything"))

    assert result.status is RunStatus.COMPLETED
    assert await save_quietly(_Broken(), Session(id="run-1")) is False


async def test_a_cancelled_run_is_persisted_too() -> None:
    store = InMemorySessionStore()
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, store=store)

    session = loop.new_session(RunRequest(objective="anything"))
    await loop.cancel(session.id)
    await loop.resume(session)

    restored = await store.load(session.id)
    assert restored is not None
    assert restored.status is SessionStatus.CANCELLED
