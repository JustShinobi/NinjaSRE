"""A question the agent raises has somewhere to appear and somewhere to be answered.

Three methods on the serving runner answered without asking anything: listing a
run's open questions returned an empty tuple unconditionally, looking one up
returned nothing, and answering one refused. That is a consistent, honest
description of a composition that bound no desk — and it made the routes behind
them permanently inert, which is not the same thing as a run having no questions.

Per run, and the tests below run two at once for the reason that matters most
here: the desk is where a question is closed, so a process-wide one would let an
answer given on one incident close the question raised by another. Of the two
things a shared binding breaks, that is the one nobody would notice.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from capabilities.registry import build_registry
from capabilities.registry.catalogue import Registry
from core.agent.handoff import HANDOFF_CAPABILITY
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
    ToolCall,
)
from core.llm.usage import TokenCounts, UsageRecord
from gateway.http.services import InvestigationStart
from gateway.runtime.investigator import NoPendingInteraction, ReActInvestigationRunner

pytestmark = pytest.mark.unit

ORG = "acme"
TEAM = "acme/payments"

#: How long a test waits for the loop to reach the question before giving up.
#: Generous enough not to be flaky, short enough that a broken composition
#: fails rather than hanging the suite.
APPEARS_WITHIN_SECONDS = 5.0


@dataclass(slots=True)
class _AskingLLM:
    """Asks a person once, then concludes with whatever they said."""

    question: str = "was the 14:02 deploy expected?"
    requests: list[InvokeRequest] = field(default_factory=list)
    turns: int = 0

    @property
    def provider_id(self) -> str:
        return "scripted"

    @property
    def model_id(self) -> str:
        return "scripted-1"

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Answer intake and diagnosis without spending a turn of the script.

        A served investigation runs the six stages, so two of its model calls
        are structured ones this double was never scripted for. Answering with
        no structured output puts both stages on the path they document for a
        provider that did not answer — intake reads the input as an incident,
        diagnosis falls back to the conclusion text — and, because it neither
        records the request nor advances the script, it leaves the turns below
        to the loop, which is where this file's assertions are.
        """
        del request, schema
        return InvokeResult(provider_id=self.provider_id, model_id=self.model_id)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        self.turns += 1
        calls: tuple[ToolCall, ...] = ()
        text = "Concluded."
        if self.turns == 1:
            calls = (
                ToolCall(
                    id="ask-1",
                    name=HANDOFF_CAPABILITY,
                    arguments={"question": self.question, "why": "only a person knows"},
                ),
            )
            text = ""
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=text,
            tool_calls=calls,
            finish_reason=FinishReason.TOOL_CALLS if calls else FinishReason.STOP,
            usage=UsageRecord(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tokens=TokenCounts(input_tokens=10, output_tokens=5),
            ),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=result.finish_reason)


def _registry() -> Registry:
    shipped = build_registry()
    found = shipped.tool(HANDOFF_CAPABILITY)
    assert found is not None
    return Registry(tools={HANDOFF_CAPABILITY: found})


def _start(run_id: str, *, principal: str = "ana") -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="checkout started erroring at 14:05",
        team_node_id=TEAM,
        principal_id=principal,
        org_id=ORG,
        alert_source="alertmanager",
    )


async def _await_question(runner: ReActInvestigationRunner, run_id: str) -> str:
    """Return the identifier of the question ``run_id`` raised, once it appears."""

    async def wait() -> str:
        while True:
            pending = await runner.pending_interactions(run_id)
            if pending:
                return pending[0].interaction_id
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(wait(), timeout=APPEARS_WITHIN_SECONDS)


async def test_a_run_that_raised_a_question_lists_it() -> None:
    runner = ReActInvestigationRunner(llm=_AskingLLM(), registry=_registry())  # type: ignore[arg-type]
    driving = asyncio.create_task(runner.investigate(_start("run-1")))

    interaction_id = await _await_question(runner, "run-1")
    pending = await runner.pending_interactions("run-1")

    assert [held.interaction_id for held in pending] == [interaction_id]
    assert pending[0].is_open
    assert "deploy" in pending[0].describe()

    await runner.answer_interaction(interaction_id, text="yes, it was planned", principal="bruno")
    await driving


async def test_answering_closes_the_question_and_reaches_the_run() -> None:
    llm = _AskingLLM()
    runner = ReActInvestigationRunner(llm=llm, registry=_registry())  # type: ignore[arg-type]
    driving = asyncio.create_task(runner.investigate(_start("run-1")))

    interaction_id = await _await_question(runner, "run-1")
    closed = await runner.answer_interaction(
        interaction_id, text="yes, it was planned", principal="bruno"
    )
    await driving

    assert not closed.is_open, "answering left the question open, so it stays on the queue"
    assert await runner.pending_interactions("run-1") == ()
    read = " ".join(repr(message) for request in llm.requests for message in request.messages)
    assert "it was planned" in read, (
        "the answer never reached the run that was waiting for it, so the agent "
        "carried on without the one fact it stopped to ask about."
    )


async def test_the_first_answer_wins_and_the_second_is_told_who_answered() -> None:
    runner = ReActInvestigationRunner(llm=_AskingLLM(), registry=_registry())  # type: ignore[arg-type]
    driving = asyncio.create_task(runner.investigate(_start("run-1")))

    interaction_id = await _await_question(runner, "run-1")
    await runner.answer_interaction(interaction_id, text="first answer", principal="bruno")
    second = await runner.answer_interaction(interaction_id, text="second answer", principal="cris")
    await driving

    assert second.answer is not None
    assert second.answer.principal == "bruno", (
        "the second answer overwrote the first. The agent already acted on what it "
        "was told, and rewriting the record makes the trace describe a run that did "
        "not happen."
    )
    assert second.answer.text == "first answer"


async def test_an_identifier_nobody_raised_is_told_apart_from_one_already_answered() -> None:
    runner = ReActInvestigationRunner(llm=_AskingLLM(), registry=_registry())  # type: ignore[arg-type]
    driving = asyncio.create_task(runner.investigate(_start("run-1")))

    interaction_id = await _await_question(runner, "run-1")
    await runner.answer_interaction(interaction_id, text="first answer", principal="bruno")

    with pytest.raises(NoPendingInteraction) as refused:
        await runner.answer_interaction("nothing-raised-this", text="hello", principal="cris")
    await driving

    said = str(refused.value)
    assert "nothing-raised-this" in said
    assert "answered" not in said, (
        f"the refusal for an identifier nobody raised reads as though it had already "
        f"been answered: {said!r}. Those are different facts and lead somewhere "
        f"different."
    )


async def test_finding_an_interaction_reaches_the_run_that_raised_it() -> None:
    runner = ReActInvestigationRunner(llm=_AskingLLM(), registry=_registry())  # type: ignore[arg-type]
    driving = asyncio.create_task(runner.investigate(_start("run-1")))

    interaction_id = await _await_question(runner, "run-1")
    found = await runner.find_interaction(interaction_id)

    assert found is not None, (
        "an interaction that was listed could not be looked up, so the route that "
        "checks which team it belongs to answers 404 for a question that exists."
    )
    assert found.run_id == "run-1"

    await runner.answer_interaction(interaction_id, text="planned", principal="bruno")
    await driving


async def test_an_answer_on_one_run_does_not_close_the_question_on_another() -> None:
    """The failure a process-wide desk produces, and the one nobody would notice."""
    runner = ReActInvestigationRunner(llm=_AskingLLM(), registry=_registry())  # type: ignore[arg-type]
    other = ReActInvestigationRunner(llm=_AskingLLM(), registry=_registry())  # type: ignore[arg-type]
    first = asyncio.create_task(runner.investigate(_start("run-1", principal="ana")))
    second = asyncio.create_task(other.investigate(_start("run-2", principal="bruno")))

    one = await _await_question(runner, "run-1")
    two = await _await_question(other, "run-2")
    assert one != two

    await runner.answer_interaction(one, text="answered on run one", principal="cris")

    assert await other.pending_interactions("run-2") != (), (
        "answering one run's question closed another run's. During an incident that "
        "is an agent proceeding on an answer nobody gave it."
    )

    await other.answer_interaction(two, text="answered on run two", principal="cris")
    await asyncio.gather(first, second)


async def test_a_run_this_process_is_not_driving_has_no_questions() -> None:
    runner = ReActInvestigationRunner(llm=_AskingLLM(), registry=_registry())  # type: ignore[arg-type]

    assert await runner.pending_interactions("never-started") == ()
    assert await runner.find_interaction("never-raised") is None


async def test_a_question_asking_for_a_credential_never_reaches_a_person() -> None:
    """Refused at the desk, before anything is raised.

    The cheapest way around a credential proxy is to ask a person to paste a
    token into a chat thread, where it would then live in the trace, the episode
    and the channel's retention for ever. So the refusal has to happen before the
    question appears anywhere — a question refused after being shown has already
    been asked of somebody, whether or not an answer came back.
    """
    llm = _AskingLLM(question="what is the API token for the metrics system?")
    runner = ReActInvestigationRunner(llm=llm, registry=_registry())  # type: ignore[arg-type]

    summary = await runner.investigate(_start("run-1"))

    assert await runner.pending_interactions("run-1") == (), (
        "a question asking for a credential was raised on the run's queue, so it "
        "reached whoever is watching it."
    )
    assert summary, "the run did not finish after the refusal"
    read = " ".join(repr(message) for request in llm.requests for message in request.messages)
    assert "token" not in read.lower() or "refus" in read.lower(), (
        "the model was not told its question was refused, so it will ask again."
    )


async def test_the_desk_a_run_gets_carries_the_shipped_window() -> None:
    """The window is the product's, not a per-run choice this composition makes.

    Asserted rather than exercised: shortening it from here would need a seam
    this composition does not have, and the behaviour at expiry — a refusal
    saying nobody answered, never a plausible guess — belongs to the desk and is
    covered where the desk is.
    """
    from config.constants.investigation import HANDOFF_TIMEOUT_SECONDS

    runner = ReActInvestigationRunner(llm=_AskingLLM(), registry=_registry())  # type: ignore[arg-type]
    desk = runner._handoff_for(_start("run-1"))

    assert desk.timeout_seconds == HANDOFF_TIMEOUT_SECONDS
    assert desk.run_id == "run-1"
