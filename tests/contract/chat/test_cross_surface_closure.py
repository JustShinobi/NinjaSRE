"""A decision made anywhere closes the approval everywhere, within budget.

The scenario the feature exists for: an approval is raised in a chat thread and
also shown in the console, somebody decides it in the console, and the button in
the thread stops being a button. The interaction layer owns the propagation;
what is asserted here is that a chat sink is a surface that propagation can
actually reach, on every platform, and that an expired interaction closes the
same way an answered one does.

A surface that only stopped showing *answered* interactions would leave exactly
the stalest questions live, which is why expiry is asserted beside the decision.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from config.constants.investigation import INTERACTION_CLOSURE_BUDGET_SECONDS
from config.constants.surfaces import SURFACE_CHAT, SURFACE_WEB_CONSOLE
from core.agent.interaction.closure import InteractionClosure, InteractionEvent
from core.agent.interaction.models import Answer, InteractionState
from core.agent.interaction.registry import InteractionRegistry
from gateway.chat.port import ChatPlatform, ChatTarget
from gateway.chat.sink import ChatSink
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.sinks import SinkGuard
from tests.contract.chat.conftest import (
    RecordingTransport,
    an_approval,
    no_wait,
    payload_texts,
)

pytestmark = pytest.mark.contract

BOTH_SURFACES = (SURFACE_CHAT, SURFACE_WEB_CONSOLE)


class _Console:
    """The other surface the approval was shown on."""

    def __init__(self) -> None:
        self.presented: list[str] = []
        self.closed_here: list[str] = []

    @property
    def name(self) -> str:
        return SURFACE_WEB_CONSOLE

    async def present(self, interaction: object) -> None:
        self.presented.append(getattr(interaction, "interaction_id", ""))

    async def closed(self, event: InteractionEvent) -> None:
        self.closed_here.append(event.interaction_id)


def _sink(platform: ChatPlatform, target: ChatTarget) -> ChatSink:
    return ChatSink(
        platform=platform,
        target=target,
        guard=SinkGuard(engine=GuardrailEngine()),
        sleep=no_wait,
    )


async def test_a_console_decision_closes_the_chat_button(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces(BOTH_SURFACES))
    chat, console = _sink(platform, target), _Console()
    closure = InteractionClosure(surfaces=[chat, console])

    await closure.present(approval)
    before = len(transport.calls)
    resolution = registry.resolve(
        approval.interaction_id,
        Answer(text="approve", principal="grace", surface=SURFACE_WEB_CONSOLE),
    )
    propagation = await closure.publish(
        InteractionEvent.of(resolution.interaction, at=approval.raised_at)
    )

    assert propagation.reached_everybody
    assert chat.closed_interactions == (approval.interaction_id,)
    # The element was actually rewritten, not merely marked closed in memory.
    assert len(transport.calls) > before
    assert "grace" in payload_texts(transport.calls[before:])


async def test_closure_reaches_chat_inside_the_propagation_budget(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces(BOTH_SURFACES))
    closure = InteractionClosure(surfaces=[_sink(platform, target), _Console()])

    resolution = registry.resolve(
        approval.interaction_id,
        Answer(text="approve", principal="grace", surface=SURFACE_WEB_CONSOLE),
    )
    propagation = await closure.publish(
        InteractionEvent.of(resolution.interaction, at=approval.raised_at)
    )

    assert propagation.within_budget
    assert propagation.budget_seconds == INTERACTION_CLOSURE_BUDGET_SECONDS


async def test_an_expired_approval_closes_in_chat_with_a_message_not_a_silent_no_op(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    """The edge case: somebody reaches for a button after the window closed."""
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces(BOTH_SURFACES))
    chat = _sink(platform, target)
    closure = InteractionClosure(surfaces=[chat])

    await closure.present(approval)
    before = len(transport.calls)
    expired = registry.expire_due(now=approval.expires_at + timedelta(seconds=1))
    assert expired and expired[0].state is InteractionState.EXPIRED
    await closure.publish(InteractionEvent.of(expired[0], at=approval.expires_at))

    said = payload_texts(transport.calls[before:])
    assert chat.closed_interactions == (approval.interaction_id,)
    assert "xpired" in said
    assert "Nothing was done" in said


async def test_a_chat_channel_that_has_gone_away_does_not_stop_the_console_closing(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces(BOTH_SURFACES))
    chat, console = _sink(platform, target), _Console()
    closure = InteractionClosure(surfaces=[chat, console])

    await closure.present(approval)
    transport.failures = [RuntimeError("channel_not_found")]
    resolution = registry.resolve(
        approval.interaction_id,
        Answer(text="approve", principal="grace", surface=SURFACE_WEB_CONSOLE),
    )
    propagation = await closure.publish(
        InteractionEvent.of(resolution.interaction, at=approval.raised_at)
    )

    assert console.closed_here == [approval.interaction_id]
    assert propagation.failed == (SURFACE_CHAT,)


async def test_an_interaction_addressed_only_to_the_console_never_reaches_chat(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    """An interaction travels only to the surfaces it names, and no others."""
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces((SURFACE_WEB_CONSOLE,)))
    chat, console = _sink(platform, target), _Console()
    closure = InteractionClosure(surfaces=[chat, console])

    await closure.present(approval)

    assert console.presented == [approval.interaction_id]
    assert transport.calls == []
