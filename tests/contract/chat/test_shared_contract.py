"""The ten shared behaviours, asserted once and run on all four platforms.

Every test here is parameterised by the ``adapter`` fixture, so a behaviour that
works on Slack and not on Discord fails one test with the platform in its id.
That is the whole claim of the feature: the marginal cost of a platform is an
adapter, not a reimplementation.
"""

from __future__ import annotations

import pytest

from config.constants.surfaces import CHAT_PLATFORMS, SURFACE_CHAT
from core.agent.interaction.closure import InteractionEvent
from core.agent.interaction.models import Answer
from gateway.chat.chunking import deliver_report
from gateway.chat.contract import CHAT_CONTRACT, missing_members, unimplemented_platforms
from gateway.chat.port import ChatPlatform, ChatTarget, PlatformLimits
from gateway.chat.session import Bindings, ChatDispatcher, SessionAction
from gateway.chat.streaming import ProgressSnapshot, ProgressStream
from tests.contract.chat.conftest import (
    ADAPTERS,
    THREAD,
    Adapter,
    RecordingTransport,
    a_question,
    an_approval,
)

pytestmark = pytest.mark.contract


# --- The contract itself covers every platform -------------------------------


def test_every_configured_platform_has_an_adapter_in_this_suite() -> None:
    """A fifth platform in the constant fails here until it has an adapter."""
    assert unimplemented_platforms([adapter.platform for adapter in ADAPTERS]) == ()
    assert len(ADAPTERS) == len(CHAT_PLATFORMS)


def test_each_adapter_has_every_member_the_contract_exercises(platform: ChatPlatform) -> None:
    assert missing_members(platform) == ()


def test_the_contract_names_ten_behaviours() -> None:
    """The plan's table, so a behaviour cannot be dropped without the count moving."""
    assert len(CHAT_CONTRACT) == 10
    assert len({behaviour.name for behaviour in CHAT_CONTRACT}) == 10


# --- 1. Start by mention or command -------------------------------------------


def test_a_mention_starts_an_investigation_bound_to_a_thread(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    message = platform.parse_message(adapter.mention())

    assert message is not None
    assert message.addressed is True
    assert "checkout" in message.text
    assert message.target.platform == adapter.platform
    assert message.target.channel_id

    dispatcher = ChatDispatcher(bindings=Bindings())
    assert dispatcher.classify(message) is SessionAction.START_INVESTIGATION


def test_a_command_is_recognised_as_a_command(adapter: Adapter, platform: ChatPlatform) -> None:
    message = platform.parse_message(adapter.command())

    assert message is not None
    assert message.is_command
    assert message.command == "status"


def test_a_started_investigation_binds_the_thread_it_answers_in(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    message = platform.parse_message(adapter.mention())
    assert message is not None

    bindings = Bindings()
    bound = bindings.bind(message.target.in_thread(message.message_id or THREAD), "run-1")

    assert bound.is_threaded
    assert bindings.run_of(bound) == "run-1"


# --- 2. Stream progress --------------------------------------------------------


async def test_progress_edits_one_message_in_place(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    clock = _Clock()
    stream = ProgressStream(platform=platform, target=target, clock=clock, sleep=_no_sleep)

    await stream.start("investigating…")
    for index in range(6):
        clock.advance(stream.interval_seconds + 0.1)
        await stream.update(ProgressSnapshot(stage=f"stage {index}", elapsed_seconds=index))

    assert stream.posts == 1
    assert stream.edits == 6
    assert stream.dropped == 0
    assert len(transport.calls) == 7


async def test_progress_coalesces_inside_the_interval_rather_than_posting_per_event(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    clock = _Clock()
    stream = ProgressStream(platform=platform, target=target, clock=clock, sleep=_no_sleep)
    await stream.start("investigating…")

    for index in range(50):
        await stream.update(ProgressSnapshot(stage=f"stage {index}"))

    assert stream.edits == 0
    assert stream.coalesced == 50

    await stream.flush()
    assert stream.edits == 1
    assert stream.last_text is not None
    assert "stage 49" in stream.last_text


# --- 3. Deliver report ---------------------------------------------------------


async def test_a_short_report_arrives_as_one_message(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    delivered = await deliver_report(platform, target, "root cause: the 14:02 deploy")

    assert len(delivered.messages) == 1
    assert delivered.attachment is None
    assert delivered.complete


async def test_an_oversized_report_is_split_and_loses_nothing(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    limit = PlatformLimits.of(platform.name).message_limit
    body = "\n".join(f"line {index} of the evidence" for index in range(limit // 8))

    delivered = await deliver_report(platform, target, body)

    assert delivered.complete
    assert delivered.recovered_text.replace("\n", "") == body.replace("\n", "")
    assert all(len(chunk) <= limit for chunk in delivered.chunks)


# --- 4. Render approval --------------------------------------------------------


def test_an_approval_renders_every_field_a_reviewer_needs(platform: ChatPlatform) -> None:
    approval = an_approval()

    element = platform.render_interaction(approval)
    rendered = f"{element.fallback_text}\n{element.payload}"

    assert approval.action in rendered
    assert approval.diff.splitlines()[0] in rendered
    assert approval.blast_radius in rendered
    assert approval.rollback_plan in rendered


def test_an_approval_is_decidable_inline(platform: ChatPlatform) -> None:
    element = platform.render_interaction(an_approval())

    assert element.choices == ("approve", "decline")
    assert element.interaction_id == "i-1"


def test_a_question_renders_its_options_and_its_reason(platform: ChatPlatform) -> None:
    question = a_question()

    element = platform.render_interaction(question)
    rendered = f"{element.fallback_text}\n{element.payload}"

    assert question.text in rendered
    assert question.reason in rendered
    assert element.choices == ("yes", "no")


# --- 5. Resolve interaction ----------------------------------------------------


def test_a_button_press_is_read_back_as_a_decision(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    decision = platform.parse_decision(adapter.decision("i-1", "approve"))

    assert decision is not None
    assert decision.interaction_id == "i-1"
    assert decision.choice == "approve"
    assert decision.user.platform == adapter.platform
    assert decision.user.user_id


async def test_closing_an_interaction_rewrites_the_element_rather_than_leaving_a_button(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    element = platform.render_interaction(an_approval())
    message = await platform.send_interaction(target, element)
    before = len(transport.calls)

    await platform.close_interaction(
        message,
        InteractionEvent.of(
            an_approval().answered_with(
                Answer(text="approve", principal="ada", surface=SURFACE_CHAT)
            ),
            at=an_approval().raised_at,
        ),
    )

    assert len(transport.calls) > before
    last = str(transport.calls[-1].payload)
    assert "ada" in last
    assert "approve" in last


# --- 6. Add mid-run context ----------------------------------------------------


def test_a_message_in_a_bound_thread_becomes_mid_run_context(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    message = platform.parse_message(adapter.plain_message())
    assert message is not None
    assert message.addressed is False

    bindings = Bindings()
    bindings.bind(message.target, "run-1")
    dispatcher = ChatDispatcher(bindings=bindings)

    assert dispatcher.classify(message) is SessionAction.ADD_CONTEXT


def test_a_message_in_an_unbound_channel_is_ignored(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    message = platform.parse_message(adapter.plain_message())
    assert message is not None

    dispatcher = ChatDispatcher(bindings=Bindings())

    assert dispatcher.classify(message) is SessionAction.IGNORE


# --- 7. Map identity -----------------------------------------------------------


def test_a_platform_user_is_read_off_every_inbound_shape(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    for payload in (adapter.mention(), adapter.command(), adapter.decision("i-1", "approve")):
        user = platform.user_of(payload)

        assert user is not None, payload
        assert user.platform == adapter.platform
        assert user.user_id


# --- 8, 9, 10 are asserted in their own modules --------------------------------
# Refusing an unmapped user: test_identity_refusal.py
# Sanitised errors: test_error_sanitisation.py
# Surviving a disconnect: test_disconnect_resilience.py


class _Clock:
    """A monotonic clock a test advances by hand."""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


async def _no_sleep(_seconds: float) -> None:
    """Do not actually wait: a backoff test should not cost wall-clock time."""
