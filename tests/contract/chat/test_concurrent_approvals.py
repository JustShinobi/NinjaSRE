"""Two people approving in two channels resolve to one decision.

The registry's conditional transition is the concurrency resolution, and this
suite's job is to prove the chat surface does not reintroduce the race on top of
it — by reading a pending set into a local list, by deciding locally before
telling the core, or by closing only the channel the winner pressed in.

The loser is told what the interaction was actually decided with, not merely
that they were late. "Somebody else approved it" and "somebody else declined it"
lead to different next actions.
"""

from __future__ import annotations

import asyncio

import pytest

from config.constants.surfaces import SURFACE_CHAT
from core.agent.interaction.closure import InteractionClosure, InteractionEvent
from core.agent.interaction.models import Answer
from core.agent.interaction.registry import InteractionRegistry
from gateway.chat.port import ChatPlatform, ChatTarget
from gateway.chat.sink import ChatSink
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.sinks import SinkGuard
from tests.contract.chat.conftest import (
    CHANNEL,
    THREAD,
    WORKSPACE,
    RecordingTransport,
    an_approval,
    no_wait,
)

pytestmark = pytest.mark.contract


def _sinks(platform: ChatPlatform) -> tuple[ChatSink, ChatSink]:
    """Return two sinks for the same platform in two different channels."""
    guard = SinkGuard(engine=GuardrailEngine())
    first = ChatTarget(
        platform=platform.name, channel_id=CHANNEL, thread_id=THREAD, workspace_id=WORKSPACE
    )
    second = ChatTarget(
        platform=platform.name, channel_id="C-platform", thread_id=THREAD, workspace_id=WORKSPACE
    )
    return (
        ChatSink(platform=platform, target=first, guard=guard, sleep=no_wait),
        ChatSink(platform=platform, target=second, guard=guard, sleep=no_wait),
    )


async def test_only_one_of_two_simultaneous_approvals_wins(platform: ChatPlatform) -> None:
    registry = InteractionRegistry(run_id="run-1")
    registry.raise_interaction(an_approval().on_surfaces((SURFACE_CHAT,)))

    resolutions = await asyncio.gather(
        _decide(registry, "ada", "approve"),
        _decide(registry, "grace", "decline"),
    )

    won = [resolution for resolution in resolutions if resolution.won]
    lost = [resolution for resolution in resolutions if not resolution.won]
    assert len(won) == 1
    assert len(lost) == 1


async def test_the_loser_is_told_what_the_decision_actually_was(
    platform: ChatPlatform,
) -> None:
    registry = InteractionRegistry(run_id="run-1")
    registry.raise_interaction(an_approval().on_surfaces((SURFACE_CHAT,)))

    first = await _decide(registry, "ada", "approve")
    second = await _decide(registry, "grace", "decline")

    assert first.won is True
    assert second.won is False
    assert second.answered_by == "ada"
    assert second.reason


async def test_one_decision_closes_the_element_in_both_channels(
    platform: ChatPlatform, transport: RecordingTransport
) -> None:
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces((SURFACE_CHAT,)))
    here, there = _sinks(platform)
    closure = InteractionClosure(surfaces=[here, there])

    await closure.present(approval)
    resolution = registry.resolve(
        approval.interaction_id, Answer(text="approve", principal="ada", surface=SURFACE_CHAT)
    )
    propagation = await closure.publish(
        InteractionEvent.of(resolution.interaction, at=approval.expires_at)
    )

    assert propagation.reached_everybody
    assert set(propagation.closed) == {SURFACE_CHAT}
    assert here.closed_interactions == (approval.interaction_id,)
    assert there.closed_interactions == (approval.interaction_id,)


async def test_a_closure_is_published_once_however_many_channels_saw_it(
    platform: ChatPlatform,
) -> None:
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces((SURFACE_CHAT,)))
    here, there = _sinks(platform)
    closure = InteractionClosure(surfaces=[here, there])

    resolution = registry.resolve(
        approval.interaction_id, Answer(text="approve", principal="ada", surface=SURFACE_CHAT)
    )
    event = InteractionEvent.of(resolution.interaction, at=approval.expires_at)
    await closure.publish(event)
    repeated = await closure.publish(event)

    assert repeated.duplicate is True
    assert here.closed_interactions == (approval.interaction_id,)


async def test_deciding_an_interaction_that_already_expired_says_so(
    platform: ChatPlatform,
) -> None:
    """The edge case: a reaction arriving after the window closed."""
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces((SURFACE_CHAT,)))
    registry.expire_due(now=approval.expires_at)

    resolution = registry.resolve(
        approval.interaction_id, Answer(text="approve", principal="ada", surface=SURFACE_CHAT)
    )

    assert resolution.won is False
    assert "expired" in resolution.reason.lower()


async def test_closing_a_channel_that_has_gone_away_does_not_stop_the_other(
    platform: ChatPlatform, transport: RecordingTransport
) -> None:
    registry = InteractionRegistry(run_id="run-1")
    approval = registry.raise_interaction(an_approval().on_surfaces((SURFACE_CHAT,)))
    here, there = _sinks(platform)
    closure = InteractionClosure(surfaces=[_Broken(), here, there])

    resolution = registry.resolve(
        approval.interaction_id, Answer(text="approve", principal="ada", surface=SURFACE_CHAT)
    )
    propagation = await closure.publish(
        InteractionEvent.of(resolution.interaction, at=approval.expires_at)
    )

    assert propagation.failed == (SURFACE_CHAT,)
    assert here.closed_interactions == (approval.interaction_id,)
    assert there.closed_interactions == (approval.interaction_id,)


async def _decide(registry: InteractionRegistry, principal: str, choice: str):  # type: ignore[no-untyped-def]
    """Resolve the one open approval as ``principal``, from a chat surface."""
    await asyncio.sleep(0)
    return registry.resolve(
        registry.pending[0].interaction_id if registry.pending else "i-1",
        Answer(text=choice, principal=principal, selected_option=choice, surface=SURFACE_CHAT),
    )


class _Broken:
    """A chat surface whose channel was archived while the approval was open."""

    @property
    def name(self) -> str:
        return SURFACE_CHAT

    async def present(self, interaction: object) -> None:
        raise RuntimeError("channel_not_found")

    async def closed(self, event: object) -> None:
        raise RuntimeError("channel_not_found")
