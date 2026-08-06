"""Asking a person, declared as a capability like everything else the agent calls.

The runtime has always had a handoff path. This is the declared form of it, and
declaring it buys three things a run-scoped closure did not: it appears in the
catalogue with its side-effect level and evidence contract stated, capability
selection can score it against everything else competing for a turn's schema
budget, and the refusal below is enforced at the same boundary every other
capability's arguments are checked at.

**The refusal is the reason this file exists.** Article IV takes credentials out
of the agent's reach by putting them behind a proxy that injects them at the
network edge. The cheapest way around that is not an exploit — it is to ask a
person to paste one into a chat thread, where it would then live in the trace,
in the episode written from the trace, and in whatever retention the channel has.
So a question that asks for a credential is refused here, before it is shown to
anybody, and the refusal tells the model what to ask instead.

Three outcomes, and they are three because the agent's next move differs for
each. An answer is something to reason from. A no-answer is a gap to record
rather than fill in. A refusal is a question to rephrase, and it is a failure
rather than an empty answer so that the model cannot read it as "nobody knew".
"""

from __future__ import annotations

from typing import Any

from capabilities.tools.system.ask_human import binding
from core.agent.handoff import (
    HANDOFF_CAPABILITY,
    SecretRequestRefused,
    refuse_secret_requests,
)
from core.capability.decorator import tool
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult, Evidence

TOOL_NAME = HANDOFF_CAPABILITY

_ASK_USE_CASES = (
    "check whether a deploy, migration, or failover happening now was intended",
    "confirm what a service is supposed to do when no runbook says",
    "ask whether an alert is a known false positive during a maintenance window",
)

_ASK_ANTI_EXAMPLES = (
    "anything another capability could establish by reading the system",
    "asking for a password, key, token, or any other credential — always refused",
    "asking a person to run a command on your behalf, which is a remediation",
)

_NOBODY_ATTACHED = (
    "No person is attached to this investigation, so this question cannot be "
    "answered. Record it as a gap in your conclusion rather than filling it in."
)


@tool(
    name=TOOL_NAME,
    display_name="Ask a person",
    description=(
        "Ask a person something only they can know — whether a change was expected, "
        "what a service is meant to do, whether an alert is a known false positive. "
        "Give a reason saying what you will do differently depending on the answer, "
        "and offer options when the question has a small closed set. You may not ask "
        "anyone for a password, key, token, or any other credential; that request is "
        "refused. If nobody answers in time you will be told so, and you must then "
        "record the gap rather than fill it in."
    ),
    domain="methodology",
    evidence_source=EvidenceSource.HUMAN,
    evidence_type=EvidenceType.DOCUMENT,
    # Reads what is in somebody's head. It changes nothing, which is exactly why
    # it must not become a way to have somebody change something on request —
    # the anti-examples say so and remediation is a different capability.
    side_effect_level=SideEffectLevel.READ,
    # Two questions arriving at one person at the same time is how both get
    # ignored, and the second one arrives with no context for why it is being
    # asked alongside the first.
    parallel_safe=False,
    tags=("human", "handoff", "clarification"),
    use_cases=_ASK_USE_CASES,
    anti_examples=_ASK_ANTI_EXAMPLES,
)
async def ask_human(
    question: str,
    why: str = "",
    options: list[str] | None = None,
) -> CapabilityResult:
    """Return a person's answer, an explicit no-answer, or a refusal.

    The refusal comes back classified ``PERMISSION_DENIED`` rather than as an
    empty answer. ``PERMISSION_DENIED`` is the classification that means "do not
    retry this", which is the correct instruction: rephrasing the same request
    for a credential produces the same refusal, and a model that read it as an
    unavailability would try three more channels.
    """
    if not question.strip():
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.INVALID_ARGUMENTS,
            "A question has to carry a question.",
        )

    try:
        refuse_secret_requests(question, why)
    except SecretRequestRefused as refused:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.PERMISSION_DENIED,
            str(refused),
            detail=f"the question asks for a {refused.term}",
        )

    desk = binding.current()
    if desk is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            _NOBODY_ATTACHED,
        )

    answered = await desk.ask(question, why=why, options=tuple(options or ()))
    if not answered.usable:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            answered.answer or _NOBODY_ATTACHED,
        )

    return CapabilityResult.ok(
        TOOL_NAME,
        value=_value(question, answered.answer, answered.principal),
        evidence=(
            Evidence(
                source=answered.principal or "a person",
                evidence_type=EvidenceType.DOCUMENT,
                summary=f"{question} — {answered.answer}",
                reference=answered.interaction_id,
            ),
        ),
    )


def _value(question: str, answer: str, principal: str) -> dict[str, Any]:
    """Return what the model reads, with the answer attributed.

    The principal is in the value rather than only in the trace. A conclusion
    resting on "the migration ran at 11:58" is worth a different amount
    depending on whether the person who said so owns that service, and the model
    cannot weigh that if the name never reaches it.
    """
    return {
        "question": question,
        "answer": answer,
        "answered_by": principal or "a person whose identity the surface did not supply",
    }


__all__ = ["TOOL_NAME", "ask_human"]
