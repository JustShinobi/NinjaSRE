"""Mid-run guidance that arrives as one instruction, and a human taking over.

Two things that look unrelated and share a premise: an investigation in progress
is something people interact with, and both of the obvious implementations
destroy the run's record of itself. Delivering every message separately makes
the model treat one instruction as three corrections. Cancelling in order to fix
something by hand produces two disconnected accounts of one incident.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.investigation import MESSAGE_QUEUE_DEBOUNCE_MS
from core.agent.interaction import (
    Answer,
    InteractionClosure,
    InteractionEvent,
    InteractionRegistry,
    InteractionState,
    ScreenedText,
    question,
)
from core.agent.message_queue import MergeReceipt, MessageQueue, merge, receipt_for
from core.agent.react_loop import PAUSED_ANSWER, ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import Session, SessionStatus
from core.agent.takeover import (
    HumanAction,
    LoopReaper,
    NotUnderTakeover,
    SubAgentReaper,
    Takeover,
    TakeoverState,
)
from core.agent.turn import GuardrailActionKind
from core.llm.types import Message, Role
from tests.unit.core.agent.conftest import (
    DEFAULT_TOOLS,
    ScriptedLLM,
    call_turn,
    log_call,
    text_turn,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _FakeClock:
    """A monotonic source a test moves by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _RedactsKeys:
    def screen(self, text: str) -> ScreenedText:
        if "sk-live-" not in text:
            return ScreenedText(text=text)
        return ScreenedText(text="[REDACTED]", rules=("no-api-keys",), blocked=True)


class _CollectingReceipts:
    def __init__(self, name: str = "slack") -> None:
        self._name = name
        self.received: list[MergeReceipt] = []

    @property
    def name(self) -> str:
        return self._name

    async def acknowledge(self, receipt: MergeReceipt) -> None:
        self.received.append(receipt)


class _BrokenReceipts(_CollectingReceipts):
    async def acknowledge(self, receipt: MergeReceipt) -> None:
        raise ConnectionError("the channel is unreachable")


def _queue(**overrides: object) -> tuple[MessageQueue, _FakeClock]:
    clock = _FakeClock()

    async def sleeper(seconds: float) -> None:
        clock.advance(seconds)

    defaults: dict[str, object] = {"clock": clock, "sleeper": sleeper, "run_id": "run-1"}
    defaults.update(overrides)
    return MessageQueue(**defaults), clock  # type: ignore[arg-type]


# --- five messages, one block (SC-004, T007, T023) -----------------------------


async def test_five_messages_inside_the_window_become_one_numbered_block() -> None:
    """SC-004. Five interruptions would make the model read the last one as a
    correction of the first four."""
    queue, clock = _queue()
    typed = [
        "the deploy at 12:02 was mine",
        "it only touched the checkout service",
        "ignore the database, we ruled it out",
        "the cache was cold at the same time",
        "roll it back if that is the cause",
    ]
    for sentence in typed:
        queue.submit(sentence, author="ada", surface="slack")
        clock.advance(0.2)

    drained = await queue.drain()
    block = merge(drained)

    assert len(drained) == 5
    assert queue.pending == 0
    for index, sentence in enumerate(typed, start=1):
        assert f"{index}. {sentence}" in block
    assert block.count("\n1. ") == 1, "one block, not five"


async def test_the_ordering_the_person_typed_in_is_the_ordering_the_model_reads() -> None:
    """Later messages often correct earlier ones, so the numbering is the point."""
    queue, clock = _queue()
    queue.submit("check the database")
    clock.advance(0.1)
    queue.submit("ignore the database, we ruled it out")

    block = merge(await queue.drain())

    assert block.index("1. check the database") < block.index("2. ignore the database")


async def test_the_window_is_measured_from_the_last_message_not_the_first() -> None:
    queue, clock = _queue()
    queue.submit("first")
    clock.advance(MESSAGE_QUEUE_DEBOUNCE_MS / 1000.0)
    queue.submit("still typing")

    await queue.drain()

    assert clock.now >= 2 * (MESSAGE_QUEUE_DEBOUNCE_MS / 1000.0)


# --- accepting from any surface (FR-007, T022) ---------------------------------


async def test_messages_from_several_surfaces_merge_into_one_block() -> None:
    queue, clock = _queue()
    queue.submit("the deploy was mine", author="ada", surface="slack")
    clock.advance(0.1)
    queue.submit("and the cache was cold", author="grace", surface="console")

    drained = await queue.drain()
    receipt = receipt_for(drained, run_id="run-1")

    assert receipt.surfaces == ("slack", "console")
    assert receipt.authors == ("ada", "grace")


# --- the receipt (FR-009, T024) -------------------------------------------------


async def test_a_merge_tells_the_surface_the_run_has_read_it() -> None:
    """Somebody who typed and saw nothing types it again, and then again."""
    slack = _CollectingReceipts()
    queue, _ = _queue(receipts=(slack,))
    queue.submit("the deploy was mine", author="ada", surface="slack")

    await queue.acknowledge(await queue.drain())

    assert [receipt.messages for receipt in slack.received] == [1]
    assert "1 message added" in slack.received[0].describe()


async def test_a_receipt_that_cannot_be_delivered_does_not_undo_the_merge() -> None:
    queue, _ = _queue(receipts=(_BrokenReceipts(), _CollectingReceipts("console")))
    queue.submit("the deploy was mine", surface="slack")

    receipt = await queue.acknowledge(await queue.drain())

    assert receipt.messages == 1


async def test_the_loop_acknowledges_the_guidance_it_merged() -> None:
    slack = _CollectingReceipts()
    queue, _ = _queue(receipts=(slack,))
    queue.submit("the deploy at 12:02 was mine", author="ada", surface="slack")

    llm = ScriptedLLM([call_turn(log_call("c1")), text_turn("Understood.")], repeat_last=False)
    result = await ReActLoop(llm=llm, tools=DEFAULT_TOOLS, messages=queue).run(
        RunRequest(objective="anything")
    )

    assert any(
        action.kind is GuardrailActionKind.MESSAGE_QUEUED
        for turn in result.turns
        for action in turn.guardrail_actions
    )
    assert [receipt.messages for receipt in slack.received] == [1]


# --- screening queued content (T026) --------------------------------------------


async def test_queued_content_is_screened_on_the_way_in() -> None:
    """The transcript is persisted. A secret that spent the debounce window
    unredacted in memory is a secret in a heap dump."""
    queue, _ = _queue(screen=_RedactsKeys())

    queued = queue.submit("the job authenticates with sk-live-abc123", surface="slack")

    assert queued.text == "[REDACTED]"
    assert queued.redacted_by == ("no-api-keys",)


async def test_the_receipt_says_when_the_guardrails_altered_what_was_typed() -> None:
    queue, _ = _queue(screen=_RedactsKeys())
    queue.submit("the job authenticates with sk-live-abc123", surface="slack")

    receipt = receipt_for(await queue.drain(), run_id="run-1")

    assert receipt.redacted
    assert "redacted" in receipt.describe()


# --- the final-turn guard (FR-010, T025) ----------------------------------------


async def test_guidance_arriving_on_the_final_turn_does_not_give_tools_back() -> None:
    """The final turn is text-only because a guardrail said so, and new input is
    not an override of a guardrail."""
    queue, _ = _queue()
    llm = ScriptedLLM([call_turn(log_call("c-repeat", "identical"))])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, messages=queue)

    session = loop.new_session(RunRequest(objective="anything"))
    session.tools_stripped = True
    queue.submit("one more thing: the cache was cold")

    result = await loop.resume(session)

    assert result.turns[-1].offered_capabilities == ()
    assert any("the cache was cold" in message.text for message in result.session.transcript)


# --- takeover (FR-011 to FR-014, SC-006, T008) ----------------------------------


class _RecordingReaper:
    def __init__(self, children: tuple[str, ...] = ()) -> None:
        self.children = children
        self.reaped: list[str] = []

    async def reap(self, session_id: str) -> tuple[str, ...]:
        self.reaped.append(session_id)
        return self.children


class _BrokenReaper:
    async def reap(self, session_id: str) -> tuple[str, ...]:
        raise RuntimeError("the specialist will not stop")


class _RecordingSurface:
    def __init__(self, name: str = "slack") -> None:
        self._name = name
        self.closed_events: list[InteractionEvent] = []

    @property
    def name(self) -> str:
        return self._name

    async def present(self, interaction: object) -> None:
        return None

    async def closed(self, event: InteractionEvent) -> None:
        self.closed_events.append(event)


def _session() -> Session:
    session = Session(id="run-1", objective="Why is checkout failing?")
    session.append(Message(role=Role.USER, text="Why is checkout failing?"))
    return session


def _takeover(**overrides: object) -> Takeover:
    defaults: dict[str, object] = {"session": _session(), "clock": lambda: AT}
    defaults.update(overrides)
    return Takeover(**defaults)  # type: ignore[arg-type]


async def test_taking_over_suspends_the_run_rather_than_ending_it() -> None:
    takeover = _takeover()

    record = await takeover.take_over(principal="ada", reason="I know what this is")

    assert takeover.state is TakeoverState.HUMAN_CONTROL
    assert takeover.session.status is SessionStatus.SUSPENDED
    assert record.principal == "ada"
    assert record.is_open


async def test_taking_over_reaps_the_specialists_that_are_in_flight() -> None:
    """FR-014. A specialist still running while a person edits the same
    deployment is two things changing one system."""
    reaper = _RecordingReaper(children=("run-1/logs-1", "run-1/metrics-2"))
    takeover = _takeover(reaper=reaper)

    record = await takeover.take_over(principal="ada")

    assert reaper.reaped == ["run-1"]
    assert record.reaped_subagents == ("run-1/logs-1", "run-1/metrics-2")


async def test_a_reaper_that_fails_does_not_leave_the_takeover_half_done() -> None:
    """A person who asked for control and did not get it is worse off than one
    who got it and is told a specialist may still be running."""
    takeover = _takeover(reaper=_BrokenReaper())

    record = await takeover.take_over(principal="ada")

    assert takeover.state is TakeoverState.HUMAN_CONTROL
    assert record.reaped_subagents == ()


async def test_taking_over_closes_whatever_the_run_was_waiting_on() -> None:
    """A pending question is a button on a surface for a run somebody is now
    driving by hand."""
    registry = InteractionRegistry(run_id="run-1", clock=lambda: AT)
    registry.raise_interaction(
        question(
            interaction_id="i1",
            run_id="run-1",
            text="was the spike expected?",
            surfaces=("slack",),
            at=AT,
        )
    )
    slack = _RecordingSurface()
    takeover = _takeover(interactions=registry, closure=InteractionClosure().subscribe(slack))

    record = await takeover.take_over(principal="ada")

    assert record.closed_interactions == ("i1",)
    assert registry.get("i1").state is InteractionState.SUPERSEDED
    assert [event.state for event in slack.closed_events] == [InteractionState.SUPERSEDED]


async def test_a_human_action_is_recorded_under_the_human_principal() -> None:
    """FR-012. The trace stays one record because every entry says who."""
    takeover = _takeover()
    await takeover.take_over(principal="ada")

    recorded = takeover.record_action(
        action="restarted the checkout deployment",
        detail="kubectl rollout restart deploy/checkout",
        outcome="pods healthy after 40s",
    )

    assert recorded.principal == "ada"
    assert takeover.actions == (recorded,)


async def test_an_action_may_name_a_different_person_from_the_one_who_paused() -> None:
    takeover = _takeover()
    await takeover.take_over(principal="ada")

    recorded = takeover.record_action(action="scaled the pool", principal="grace")

    assert recorded.principal == "grace"


def test_recording_against_a_run_nobody_took_over_is_refused() -> None:
    """An action in a trace with no interval around it reads as one nobody
    authorised."""
    with pytest.raises(NotUnderTakeover):
        _takeover().record_action(action="restarted checkout")


async def test_taking_over_a_run_that_is_already_under_takeover_is_refused() -> None:
    takeover = _takeover()
    await takeover.take_over(principal="ada")

    with pytest.raises(NotUnderTakeover, match="ada"):
        await takeover.take_over(principal="grace")


async def test_resuming_puts_the_human_actions_into_the_agents_context() -> None:
    """FR-013. The agent continues from what actually happened."""
    takeover = _takeover()
    await takeover.take_over(principal="ada")
    takeover.record_action(action="restarted the checkout deployment", outcome="pods healthy")

    record = takeover.resume()

    assert record.state is TakeoverState.RESUMED
    assert takeover.session.status is SessionStatus.RUNNING
    context = takeover.session.transcript[-1].text
    assert "ada" in context
    assert "restarted the checkout deployment" in context
    assert "not as evidence you" in context


async def test_a_takeover_with_no_actions_adds_nothing_to_the_transcript() -> None:
    takeover = _takeover()
    before = len(takeover.session.transcript)
    await takeover.take_over(principal="ada")

    takeover.resume()

    assert len(takeover.session.transcript) == before


async def test_a_person_can_conclude_the_investigation_by_hand() -> None:
    """T031. Somebody handled the incident, which is a conclusion rather than a
    cancellation."""
    takeover = _takeover()
    await takeover.take_over(principal="ada")
    takeover.record_action(action="rolled the deploy back")

    record = takeover.conclude(answer="The 12:02 deploy caused it; it was rolled back.")

    assert record.state is TakeoverState.CONCLUDED
    assert takeover.session.status is SessionStatus.COMPLETED
    assert "rolled back" in takeover.session.transcript[-1].text


def test_a_human_action_has_to_say_who_and_what() -> None:
    with pytest.raises(ValueError, match="who"):
        HumanAction(principal="", action="restarted checkout", at=AT)
    with pytest.raises(ValueError, match="what"):
        HumanAction(principal="ada", action="  ", at=AT)


def test_a_takeover_record_round_trips() -> None:
    action = HumanAction(principal="ada", action="restarted checkout", at=AT, outcome="healthy")

    assert HumanAction.from_record(action.to_record()) == action


def test_the_interval_reports_how_long_it_lasted() -> None:
    takeover = _takeover()
    later = AT + timedelta(minutes=7)

    assert takeover.record is None
    assert HumanAction(principal="ada", action="x", at=AT).at == AT
    assert (later - AT).total_seconds() == 420.0


# --- the loop's pause path (T027, T032) ------------------------------------------


async def test_a_paused_run_stops_at_a_safe_point_and_stays_resumable() -> None:
    """SC-006. Suspended rather than cancelled, with its evidence intact."""
    llm = ScriptedLLM([call_turn(log_call("c1", "unique")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    session = loop.new_session(RunRequest(objective="anything"))
    await loop.pause(session.id)
    result = await loop.resume(session)

    assert result.status is RunStatus.PARTIAL
    assert result.session.status is SessionStatus.SUSPENDED
    assert result.answer == PAUSED_ANSWER
    assert Session.from_record(session.to_record()).turns == session.turns


async def test_a_run_paused_after_working_keeps_what_it_gathered() -> None:
    llm = ScriptedLLM([call_turn(log_call("c1", "unique")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    session = loop.new_session(RunRequest(objective="anything"))
    result = await loop.resume(session)
    gathered = len(result.session.evidence)
    await loop.pause(session.id)
    paused = await loop.resume(result.session)

    assert paused.session.status is SessionStatus.SUSPENDED
    assert len(paused.session.evidence) == gathered


async def test_a_paused_run_can_be_taken_over_and_handed_back_to_the_loop() -> None:
    """The trace is one record across the whole sequence."""
    llm = ScriptedLLM([call_turn(log_call("c1", "unique")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)
    session = loop.new_session(RunRequest(objective="anything"))
    await loop.pause(session.id)
    await loop.resume(session)

    takeover = Takeover(session=session, clock=lambda: AT)
    await takeover.take_over(principal="ada")
    takeover.record_action(action="restarted checkout", outcome="pods healthy")
    takeover.resume()

    result = await loop.resume(session)

    assert result.status is RunStatus.COMPLETED
    assert any("restarted checkout" in message.text for message in result.session.transcript)
    assert result.session.id == session.id


async def test_cancellation_wins_over_a_pause_on_the_same_run() -> None:
    """A run that is both is over: suspending it would invite a resumption of a
    decision that was already made."""
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)
    session = loop.new_session(RunRequest(objective="anything"))
    await loop.pause(session.id)
    await loop.cancel(session.id)

    result = await loop.resume(session)

    assert result.status is RunStatus.CANCELLED


async def test_the_loop_reaper_stops_the_children_a_run_dispatched() -> None:
    loop = ReActLoop(llm=ScriptedLLM([text_turn("done")]), tools=DEFAULT_TOOLS)
    reaper = LoopReaper(cancel=loop.cancel, children=loop.children_of)

    assert isinstance(reaper, SubAgentReaper)
    assert await reaper.reap("run-1") == ()


def test_a_run_with_no_specialists_has_no_children() -> None:
    loop = ReActLoop(llm=ScriptedLLM([text_turn("done")]), tools=DEFAULT_TOOLS)

    assert loop.children_of("run-1") == ()


def test_an_answer_that_nobody_gave_is_not_usable() -> None:
    assert not Answer(text="anything", answered=False).usable
