"""Asking a human, refusing to ask for the wrong thing, and what an expiry means.

Some things are only in somebody's head: whether the migration ran, whether the
traffic spike was the marketing launch, whether this alert is expected during a
failover test. An agent that cannot ask will infer, and an inference presented
as a finding is the failure mode Article I exists to prevent.

Three rules shape everything here.

**The expiry gives a refusal, never a guess.** On timeout the agent is told the
answer is *unavailable*. An agent that learns it gets a plausible answer when
nobody replies has learned that asking is optional, and it will stop asking
exactly when the question mattered.

**The agent may not ask for a secret.** Article IV removes credentials from the
agent's reach by putting them behind a proxy, and the cheapest way around that
is to ask a person to paste one into a chat thread — where it would then live in
the trace, the episode, and the channel's retention forever. So a question that
requests a credential is refused at this boundary, before it reaches anybody.
The guardrail screen on the answer is the second line: a person who volunteers a
secret in reply to an innocent question has it redacted before the agent sees it.

**A question is an interaction.** It goes into the run's registry, it is shown
on the surfaces the run is routed to, the first answer wins, and answering it
anywhere closes it everywhere. None of that is implemented here — it is in
``core.agent.interaction``, shared with approvals, which is the point.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.investigation import HANDOFF_TIMEOUT_SECONDS, INTERACTION_EXPIRY_SECONDS
from config.prompts.investigation import HANDOFF_TIMED_OUT
from core.agent.interaction.closure import InteractionClosure
from core.agent.interaction.models import (
    NO_SURFACE,
    Answer,
    ContentFilter,
    Interaction,
    Question,
    Resolution,
    screen_with,
)
from core.agent.interaction.models import (
    question as build_question,
)
from core.agent.interaction.registry import InteractionRegistry
from core.capability.metadata import (
    EvidenceSource,
    EvidenceType,
    SideEffectLevel,
    ToolMetadata,
)
from core.capability.registered import RegisteredTool, build_registration
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The name the model calls to put a question to a person.
HANDOFF_CAPABILITY = "ask_human"

_HANDOFF_DESCRIPTION = (
    "Ask a person something only they can know — whether a change was expected, "
    "what a service is meant to do, whether an alert is a known false positive. "
    "Use it when an inference would be a guess; do not use it for anything you "
    "could establish with another capability. You may not ask anyone for a "
    "password, key, token, or any other credential — that request is refused. "
    "If nobody answers in time you will be told so, and you must then record the "
    "gap rather than fill it in."
)

_HANDOFF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": (
                "The question, standing on its own. The person reading it may not "
                "have followed the investigation."
            ),
        },
        "why": {
            "type": "string",
            "description": "What you will do differently depending on the answer.",
        },
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Answers to offer, when the question has a small closed set.",
        },
    },
    "required": ["question"],
}


# --- refusing to ask for a secret (FR-006) -----------------------------------

#: What a credential is called when somebody asks for one. Broad on purpose: the
#: cost of a false positive is one question the agent has to rephrase, and the
#: cost of a false negative is a live secret in an incident channel forever.
CREDENTIAL_TERMS: Final[tuple[str, ...]] = (
    "access key",
    "api key",
    "api token",
    "auth token",
    "bearer token",
    "client secret",
    "credential",
    "passphrase",
    "password",
    "private key",
    "secret key",
    "service account key",
    "session token",
    "ssh key",
)

#: The phrasings that turn naming a credential into asking for its value. A
#: question that merely *mentions* one — "was the API key rotated at 11:58?" —
#: is a legitimate question about the world, and refusing it would teach the
#: agent that the whole subject is off limits rather than the disclosure is.
DISCLOSURE_PHRASES: Final[tuple[str, ...]] = (
    "can you send",
    "can you share",
    "give me",
    "hand me",
    "paste",
    "provide the",
    "send me",
    "share the",
    "tell me the",
    "what is the",
    "what's the",
)

#: A credential offered rather than asked for. "Here is the token" in a question
#: is the agent trying to launder one through the transcript.
_DISCLOSURE_PATTERN: Final = re.compile(
    r"\b(?:here (?:is|are)|the value of|copy of)\b",
    re.IGNORECASE,
)


class SecretRequestRefused(ValueError):
    """A question that asks somebody for a credential.

    Raised rather than returned by the checker, because the two callers — the
    runtime tool and the declared capability — both turn it into a refusal the
    model can read, and an exception is what stops a third caller from
    forgetting to check the return value.
    """

    def __init__(self, term: str) -> None:
        super().__init__(term)
        self.term = term

    def __str__(self) -> str:
        return (
            f"This question asks somebody to disclose a {self.term}, and that is refused. "
            f"Credentials are held by the credential proxy and are never seen by you, by a "
            f"person answering a question, or by this investigation's trace. If you need an "
            f"authenticated call, make it through the capability that owns it. If you need to "
            f"know whether a credential is valid, expired, or rotated, ask that instead."
        )


def secret_request_term(*parts: str) -> str:
    """Return the credential a question asks for, or the empty string.

    Takes the question and its stated reason together, because "what is the
    value?" is innocent on its own and is not once the reason says which value.
    """
    text = " ".join(part for part in parts if part).lower()
    if not text:
        return ""

    named = next((term for term in CREDENTIAL_TERMS if term in text), "")
    if not named:
        return ""

    asks = any(phrase in text for phrase in DISCLOSURE_PHRASES) or bool(
        _DISCLOSURE_PATTERN.search(text)
    )
    return named if asks else ""


def refuse_secret_requests(*parts: str) -> None:
    """Raise ``SecretRequestRefused`` if these parts ask for a credential."""
    term = secret_request_term(*parts)
    if term:
        raise SecretRequestRefused(term)


# --- the values a handoff exchanges ------------------------------------------


@dataclass(frozen=True, slots=True)
class HandoffQuestion:
    """One question on its way to a person."""

    question: str
    why: str = ""
    options: tuple[str, ...] = ()
    session_id: str = ""
    #: Where it is shown: the surface the investigation came from, first, then
    #: whatever the team configured for escalation.
    surfaces: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("a handoff must carry a question")


@dataclass(frozen=True, slots=True)
class HandoffAnswer:
    """What came back, or the fact that nothing did.

    ``principal`` is who answered. It is empty for a no-answer and for the
    channels that have no notion of identity, and it is what the trace records
    so that a conclusion resting on "Ada said the migration ran" can be followed
    up with Ada.
    """

    answer: str
    answered: bool = True
    principal: str = ""
    surface: str = ""
    selected_option: str = ""
    interaction_id: str = ""
    refused: bool = False
    redacted_by: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Return whether the agent may reason from this."""
        return self.answered and bool(self.answer.strip())

    @property
    def redacted(self) -> bool:
        """Return whether the guardrails altered what the person wrote."""
        return bool(self.redacted_by)

    def to_record(self) -> dict[str, Any]:
        """Return the form the tool result and the trace carry."""
        record: dict[str, Any] = {"answer": self.answer, "answered": self.answered}
        if self.principal:
            record["answered_by"] = self.principal
        if self.refused:
            record["refused"] = True
        if self.redacted_by:
            record["redacted_by"] = list(self.redacted_by)
        return record

    @classmethod
    def of(cls, answer: Answer, *, interaction_id: str = "") -> HandoffAnswer:
        """Return the runtime's view of an interaction's answer."""
        return cls(
            answer=answer.text,
            answered=answer.answered,
            principal=answer.principal,
            surface=answer.surface,
            selected_option=answer.selected_option,
            interaction_id=interaction_id,
            redacted_by=answer.redacted_by,
        )


@runtime_checkable
class HandoffChannel(Protocol):
    """Where a question reaches a person, and their answer comes back."""

    async def ask(self, question: HandoffQuestion) -> HandoffAnswer:
        """Return the person's answer to ``question``."""


@dataclass(frozen=True, slots=True)
class NoHumanAvailable:
    """The default channel: there is nobody attached to this run.

    Answers immediately rather than waiting out the timeout. A batch run with no
    surface attached would otherwise spend fifteen minutes per question
    discovering something it knew when it started.
    """

    async def ask(self, question: HandoffQuestion) -> HandoffAnswer:
        """Return the unavailable answer, without waiting."""
        return HandoffAnswer(
            answer=(
                "No person is attached to this investigation, so this question cannot "
                "be answered. Record it as a gap in your conclusion."
            ),
            answered=False,
        )


async def ask_human(
    channel: HandoffChannel,
    question: HandoffQuestion,
    *,
    timeout_seconds: float = HANDOFF_TIMEOUT_SECONDS,
) -> HandoffAnswer:
    """Return the answer to ``question``, or the refusal an expiry produces.

    Default-deny on expiry, and on a channel that raised: both mean nobody
    answered, and both must reach the model as the same unambiguous fact.
    """
    try:
        refuse_secret_requests(question.question, question.why)
    except SecretRequestRefused as refused:
        logger.warning(
            "agent.handoff_refused",
            session_id=question.session_id,
            term=refused.term,
        )
        return HandoffAnswer(answer=str(refused), answered=False, refused=True)

    try:
        return await asyncio.wait_for(channel.ask(question), timeout=timeout_seconds)
    except TimeoutError:
        logger.info(
            "agent.handoff_timed_out",
            session_id=question.session_id,
            seconds=timeout_seconds,
        )
        return HandoffAnswer(
            answer=HANDOFF_TIMED_OUT.format(seconds=timeout_seconds), answered=False
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001 — a broken surface is still "no answer"
        logger.warning("agent.handoff_failed", session_id=question.session_id, error=str(error))
        return HandoffAnswer(
            answer=(
                "The question could not be delivered to anyone "
                f"({type(error).__name__}). Record it as a gap in your conclusion."
            ),
            answered=False,
        )


# --- the desk: raise, suspend, await, close ----------------------------------


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(slots=True)
class HumanHandoff:
    """Puts a question to people on behalf of one run, and waits for one answer.

    The loop calls ``ask`` and suspends inside it. Any surface calls ``answer``,
    from anywhere, and the loop wakes with whatever that surface supplied — which
    is what makes "answered in the console" and "answered in Slack" the same
    code path rather than two that drift.

    ``channel`` is optional and is the non-interactive path: a CLI prompt, a
    fake in a test, the "nobody is attached" default. When one is supplied it
    races the surfaces, and the first of the two to produce an answer wins
    through the registry like any other answer would.
    """

    registry: InteractionRegistry
    closure: InteractionClosure | None = None
    screen: ContentFilter | None = None
    channel: HandoffChannel | None = None
    run_id: str = ""
    #: Where questions go: the originating surface first, then the escalation
    #: surfaces the team configured (FR-002).
    surfaces: tuple[str, ...] = ()
    timeout_seconds: float = HANDOFF_TIMEOUT_SECONDS
    expiry_seconds: float = INTERACTION_EXPIRY_SECONDS
    clock: Callable[[], datetime] = _utc_now
    _waiting: dict[str, asyncio.Future[Answer]] = field(default_factory=dict, repr=False)

    # -- asking ---------------------------------------------------------------

    async def ask(
        self,
        text: str,
        *,
        why: str = "",
        options: Sequence[str] = (),
    ) -> HandoffAnswer:
        """Raise ``text`` as a question, wait for one answer, and return it.

        Refused before anything is raised when the question asks for a
        credential: a refused question must not appear on a surface at all, or
        the request has been made of a person whether or not the agent got an
        answer.
        """
        try:
            refuse_secret_requests(text, why)
        except SecretRequestRefused as refused:
            logger.warning("agent.handoff_refused", run_id=self.run_id, term=refused.term)
            return HandoffAnswer(answer=str(refused), answered=False, refused=True)

        raised = self._raise(text, why=why, options=tuple(options))
        await self._present(raised)

        waiter: asyncio.Future[Answer] = asyncio.get_running_loop().create_future()
        self._waiting[raised.interaction_id] = waiter
        try:
            answer = await self._await_answer(raised, waiter)
        finally:
            self._waiting.pop(raised.interaction_id, None)

        return HandoffAnswer.of(answer, interaction_id=raised.interaction_id)

    def _raise(self, text: str, *, why: str, options: tuple[str, ...]) -> Question:
        """Return the question, registered as pending on this run."""
        raised = build_question(
            interaction_id=self.registry.next_identifier(),
            run_id=self.run_id or self.registry.run_id,
            text=text,
            reason=why,
            options=options,
            surfaces=self.surfaces or (NO_SURFACE,),
            at=self.clock(),
            expiry_seconds=self.expiry_seconds,
        )
        self.registry.raise_interaction(raised)
        return raised

    async def _present(self, raised: Interaction) -> None:
        """Show the question wherever the run is routed."""
        if self.closure is None:
            return
        shown = await self.closure.present(raised)
        if not shown:
            # Not a failure: a run with no surface attached still asks, gets
            # nothing, and concludes with the gap recorded. Worth a line,
            # because "nobody could have answered" explains a conclusion that
            # otherwise looks like the agent gave up early.
            logger.info(
                "agent.question_reached_nobody",
                run_id=raised.run_id,
                interaction_id=raised.interaction_id,
                surfaces=list(raised.surfaces),
            )

    async def _await_answer(self, raised: Question, waiter: asyncio.Future[Answer]) -> Answer:
        """Return the answer, or the value an expiry or a broken channel produces.

        Two racers when a channel is configured, and the loser is cancelled
        rather than left running. A channel still waiting on a CLI prompt after
        a Slack answer arrived is a prompt somebody will type into, and the
        registry would refuse it — but only after they had typed it.
        """
        racing: list[asyncio.Task[Answer]] = [asyncio.ensure_future(waiter)]
        channel = self.channel
        if channel is not None:
            racing.append(asyncio.ensure_future(self._through_channel(raised, channel)))

        done, unfinished = await asyncio.wait(
            racing, timeout=self.timeout_seconds, return_when=asyncio.FIRST_COMPLETED
        )
        for task in unfinished:
            task.cancel()

        if not done:
            return await self._expire(raised)

        settled = next(iter(done))
        try:
            answered = settled.result()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — a broken surface is still "no answer"
            logger.warning(
                "agent.handoff_failed",
                run_id=raised.run_id,
                interaction_id=raised.interaction_id,
                error=str(error),
            )
            return await self._expire(
                raised,
                text=(
                    "The question could not be delivered to anyone "
                    f"({type(error).__name__}). Record it as a gap in your conclusion."
                ),
            )

        if not answered.answered:
            # The channel said nobody can answer, and the loop is about to
            # continue without one. Leaving the question open would leave a
            # button on every surface for a run that has already moved past it.
            await self._close_unanswered(raised)
        return answered

    async def _close_unanswered(self, raised: Question) -> None:
        """Close a question the run is continuing without, and say so everywhere."""
        superseded = tuple(
            closed
            for closed in self.registry.supersede_open(reason="the run continued without an answer")
            if closed.interaction_id == raised.interaction_id
        )
        await self._publish(superseded)

    async def _through_channel(self, raised: Question, channel: HandoffChannel) -> Answer:
        """Return the channel's answer, put through the registry like any other."""
        replied = await channel.ask(
            HandoffQuestion(
                question=raised.text,
                why=raised.reason,
                options=raised.options,
                session_id=raised.run_id,
                surfaces=raised.surfaces,
            )
        )
        if not replied.answered:
            # The channel declining is not a closure: a surface may still
            # answer, and on timeout the expiry path closes it once.
            return Answer(text=replied.answer, answered=False, surface=replied.surface)

        resolution = await self.answer(
            raised.interaction_id,
            text=replied.answer,
            principal=replied.principal,
            surface=replied.surface,
            selected_option=replied.selected_option,
        )
        return resolution.interaction.answer or Answer(text=replied.answer, answered=False)

    async def _expire(self, raised: Question, *, text: str = "") -> Answer:
        """Close the question as expired, tell every surface, and refuse to guess."""
        lapsed = self.registry.expire_due(max(self.clock(), raised.expires_at))
        await self._publish(lapsed)
        logger.info(
            "agent.handoff_timed_out",
            run_id=raised.run_id,
            interaction_id=raised.interaction_id,
            seconds=self.timeout_seconds,
        )
        return Answer(
            text=text or HANDOFF_TIMED_OUT.format(seconds=self.timeout_seconds),
            answered=False,
        )

    # -- answering ------------------------------------------------------------

    async def answer(
        self,
        interaction_id: str,
        *,
        text: str,
        principal: str,
        surface: str = "",
        selected_option: str = "",
    ) -> Resolution:
        """Answer ``interaction_id`` as ``principal``, and close it everywhere.

        Screened before it is stored, not after. An answer that reached the
        registry unredacted is an answer in the session record, and the session
        record is persisted — redacting it on the way to the model would leave
        the secret in the one place it lives longest.
        """
        screened = screen_with(self.screen, text)
        recorded = Answer(
            text=screened.text,
            principal=principal,
            answered_at=self.clock(),
            selected_option=selected_option,
            surface=surface,
            redacted_by=screened.rules,
        )
        resolution = self.registry.resolve(interaction_id, recorded)

        if resolution.won:
            await self._publish((resolution.interaction,))
            waiter = self._waiting.get(interaction_id)
            if waiter is not None and not waiter.done():
                waiter.set_result(recorded)
            if screened.altered:
                logger.info(
                    "agent.answer_redacted",
                    run_id=resolution.interaction.run_id,
                    interaction_id=interaction_id,
                    rules=list(screened.rules),
                )
        return resolution

    async def _publish(self, closed: Sequence[Interaction]) -> None:
        """Tell every surface about each of ``closed``, once."""
        if self.closure is None or not closed:
            return
        await self.closure.publish_all(closed, at=self.clock())

    # -- the capability -------------------------------------------------------

    def tool(self) -> RegisteredTool:
        """Return the capability that puts a question to a person through this desk."""

        async def ask(
            question: str, why: str = "", options: list[str] | None = None
        ) -> dict[str, Any]:
            answered = await self.ask(question, why=why, options=tuple(options or ()))
            return answered.to_record()

        return _registration(ask)


def handoff_tool(
    channel: HandoffChannel,
    *,
    session_id: str = "",
    timeout_seconds: float = HANDOFF_TIMEOUT_SECONDS,
) -> RegisteredTool:
    """Return the capability that puts a question to a person over ``channel``.

    Built per run rather than declared once, because the channel and the session
    it belongs to are both run-scoped. Declared ``parallel_safe=False``: two
    questions arriving at one person at the same time is how both get ignored.
    """

    async def ask(question: str, why: str = "", options: list[str] | None = None) -> dict[str, Any]:
        answered = await ask_human(
            channel,
            HandoffQuestion(
                question=question,
                why=why,
                options=tuple(options or ()),
                session_id=session_id,
            ),
            timeout_seconds=timeout_seconds,
        )
        return answered.to_record()

    return _registration(ask)


def _registration(call: Callable[..., Any]) -> RegisteredTool:
    """Return the declaration both handoff paths register under.

    One declaration, so the model sees the same schema and the same refusal
    warning whether the run was wired with a desk or with a bare channel. Two
    would be two chances for one of them to lose the sentence about credentials.
    """
    return build_registration(
        metadata=ToolMetadata(
            name=HANDOFF_CAPABILITY,
            display_name="Ask a person",
            description=_HANDOFF_DESCRIPTION,
            domain="methodology",
            tags=("human", "handoff", "clarification"),
            evidence_source=EvidenceSource.HUMAN,
            evidence_type=EvidenceType.DOCUMENT,
            side_effect_level=SideEffectLevel.READ,
            parallel_safe=False,
        ),
        call=call,
        source_module=__name__,
        source_qualname="handoff_tool.ask",
        input_schema=_HANDOFF_SCHEMA,
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}, "answered": {"type": "boolean"}},
            "required": ["answer", "answered"],
        },
    )


def with_escalation(origin: str, escalation: Sequence[str]) -> tuple[str, ...]:
    """Return the surfaces a question is routed to, origin first (FR-002).

    Deduplicated, and the origin stays first however the escalation list is
    written. The person who started the investigation is the one most likely to
    know, and a routing order that put them third is a question they see after
    somebody else has already been paged about it.
    """
    ordered = [origin or NO_SURFACE]
    for surface in escalation:
        if surface and surface not in ordered:
            ordered.append(surface)
    return tuple(ordered)


__all__ = [
    "CREDENTIAL_TERMS",
    "DISCLOSURE_PHRASES",
    "HANDOFF_CAPABILITY",
    "HandoffAnswer",
    "HandoffChannel",
    "HandoffQuestion",
    "HumanHandoff",
    "NoHumanAvailable",
    "SecretRequestRefused",
    "ask_human",
    "handoff_tool",
    "refuse_secret_requests",
    "secret_request_term",
    "with_escalation",
]
