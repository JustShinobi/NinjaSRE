"""Asking a human, and what happens when nobody answers.

Some things are only in somebody's head: whether the migration ran, whether the
traffic spike was the marketing launch, whether this alert is expected during a
failover test. An agent that cannot ask will infer, and an inference presented
as a finding is the failure mode Article I exists to prevent.

The expiry rule is the whole design. On timeout the agent is told the answer is
**unavailable** — never given a default, never given a guess. An agent that
learns it gets a plausible answer when nobody replies has learned that asking is
optional, and it will stop asking exactly when the question mattered.

The channel is a port. Rendering a question at a CLI, in a chat thread, or in
the web console is features 018 to 023; the runtime needs only "ask, and tell me
what came back or that nothing did".
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from config.constants.investigation import HANDOFF_TIMEOUT_SECONDS
from config.prompts.investigation import HANDOFF_TIMED_OUT
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
    "could establish with another capability. If nobody answers in time you will "
    "be told so, and you must then record the gap rather than fill it in."
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


@dataclass(frozen=True, slots=True)
class HandoffQuestion:
    """One question on its way to a person."""

    question: str
    why: str = ""
    options: tuple[str, ...] = ()
    session_id: str = ""

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("a handoff must carry a question")


@dataclass(frozen=True, slots=True)
class HandoffAnswer:
    """What came back, or the fact that nothing did."""

    answer: str
    answered: bool = True

    @property
    def usable(self) -> bool:
        """Return whether the agent may reason from this."""
        return self.answered and bool(self.answer.strip())


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


def handoff_tool(
    channel: HandoffChannel,
    *,
    session_id: str = "",
    timeout_seconds: float = HANDOFF_TIMEOUT_SECONDS,
) -> RegisteredTool:
    """Return the capability that puts a question to a person.

    Built per run rather than declared once, because the channel and the session
    it belongs to are both run-scoped. Declared ``parallel_safe=False``: two
    questions arriving at one person at the same time is how both get ignored.
    """

    async def ask(question: str, why: str = "", options: list[str] | None = None) -> dict[str, Any]:
        answer = await ask_human(
            channel,
            HandoffQuestion(
                question=question,
                why=why,
                options=tuple(options or ()),
                session_id=session_id,
            ),
            timeout_seconds=timeout_seconds,
        )
        return {"answer": answer.answer, "answered": answer.answered}

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
        call=ask,
        source_module=__name__,
        source_qualname="handoff_tool.ask",
        input_schema=_HANDOFF_SCHEMA,
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}, "answered": {"type": "boolean"}},
            "required": ["answer", "answered"],
        },
    )


__all__ = [
    "HANDOFF_CAPABILITY",
    "HandoffAnswer",
    "HandoffChannel",
    "HandoffQuestion",
    "NoHumanAvailable",
    "ask_human",
    "handoff_tool",
]
