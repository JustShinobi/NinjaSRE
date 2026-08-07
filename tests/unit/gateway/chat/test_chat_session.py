"""What an inbound message means, who may do it, and which thread carries a run.

Classification and authorisation are tested apart because they fail apart: a
message misclassified as "start a run" is a duplicate investigation, and a
message correctly classified but wrongly authorised is somebody approving a
rollback they may not approve.
"""

from __future__ import annotations

import pytest

from config.constants.surfaces import CHAT_PLATFORM_SLACK
from gateway.chat.identity import ChatIdentity, IdentityResolver, MappingIdentityDirectory
from gateway.chat.port import ChatTarget, InboundMessage, PlatformUser
from gateway.chat.routing import ChannelRouting, RoutingTable
from gateway.chat.session import Bindings, ChatDispatcher, SessionAction
from platform.identity.permissions import Role

pytestmark = pytest.mark.unit

CHANNEL = ChatTarget(
    platform=CHAT_PLATFORM_SLACK, channel_id="C-pay", thread_id="", workspace_id="W1"
)
THREAD = CHANNEL.in_thread("T1")
ADA = PlatformUser(
    platform=CHAT_PLATFORM_SLACK, user_id="U-ada", display_name="Ada", workspace_id="W1"
)
STRANGER = PlatformUser(platform=CHAT_PLATFORM_SLACK, user_id="U-nobody", workspace_id="W1")


def _message(
    *,
    target: ChatTarget = THREAD,
    user: PlatformUser = ADA,
    text: str = "what is happening with checkout?",
    addressed: bool = False,
    command: str = "",
) -> InboundMessage:
    return InboundMessage(target=target, user=user, text=text, addressed=addressed, command=command)


def _resolver(*, role: Role = Role.RESPONDER) -> IdentityResolver:
    return IdentityResolver(
        directory=MappingIdentityDirectory(
            identities=(
                ChatIdentity(
                    platform=CHAT_PLATFORM_SLACK,
                    platform_user_id="U-ada",
                    workspace_id="W1",
                    principal_id="ada",
                    node_id="payments",
                ),
            ),
            roles={"ada": role},
        )
    )


def _routing() -> RoutingTable:
    return RoutingTable.of(
        [
            ChannelRouting(
                platform=CHAT_PLATFORM_SLACK,
                channel_id="C-pay",
                team_id="payments",
                workspace_id="W1",
            )
        ]
    )


# --- Bindings -------------------------------------------------------------------


def test_a_thread_carries_one_run() -> None:
    bindings = Bindings()

    bindings.bind(THREAD, "run-1")

    assert bindings.run_of(THREAD) == "run-1"
    assert bindings.target_of("run-1") == THREAD


def test_two_threads_in_one_channel_carry_two_runs() -> None:
    """One channel routinely holds three incidents at once."""
    bindings = Bindings()
    first, second = CHANNEL.in_thread("T1"), CHANNEL.in_thread("T2")

    bindings.bind(first, "run-1")
    bindings.bind(second, "run-2")

    assert bindings.run_of(first) == "run-1"
    assert bindings.run_of(second) == "run-2"
    assert len(bindings) == 2


def test_binding_without_a_thread_is_refused() -> None:
    with pytest.raises(ValueError, match="without a thread"):
        Bindings().bind(CHANNEL, "run-1")


def test_releasing_a_binding_returns_the_run_it_was_carrying() -> None:
    bindings = Bindings()
    bindings.bind(THREAD, "run-1")

    assert bindings.release(THREAD) == "run-1"
    assert bindings.run_of(THREAD) == ""
    assert bindings.target_of("run-1") is None


def test_an_unbound_thread_reports_no_run_rather_than_raising() -> None:
    assert Bindings().run_of(THREAD) == ""


# --- Classification -------------------------------------------------------------


def test_a_mention_in_an_unbound_thread_starts_an_investigation() -> None:
    dispatcher = ChatDispatcher(bindings=Bindings())

    assert dispatcher.classify(_message(addressed=True)) is SessionAction.START_INVESTIGATION


def test_a_message_in_a_bound_thread_is_context_even_when_it_mentions_the_bot() -> None:
    """Following a thread is the point: re-tagging must not start a second run."""
    bindings = Bindings()
    bindings.bind(THREAD, "run-1")
    dispatcher = ChatDispatcher(bindings=bindings)

    assert dispatcher.classify(_message(addressed=True)) is SessionAction.ADD_CONTEXT


def test_an_unaddressed_message_in_an_unbound_thread_is_ignored() -> None:
    dispatcher = ChatDispatcher(bindings=Bindings())

    assert dispatcher.classify(_message()) is SessionAction.IGNORE


def test_a_command_is_a_command_wherever_it_arrives() -> None:
    bindings = Bindings()
    bindings.bind(THREAD, "run-1")
    dispatcher = ChatDispatcher(bindings=bindings)

    assert dispatcher.classify(_message(command="status")) is SessionAction.RUN_COMMAND


# --- Dispatch: routing ----------------------------------------------------------


async def test_an_unrouted_channel_is_refused_with_a_reason() -> None:
    dispatcher = ChatDispatcher(bindings=Bindings(), routing=RoutingTable.of([]))

    dispatch = await dispatcher.dispatch(_message(addressed=True))

    assert dispatch.action is SessionAction.IGNORE
    assert dispatch.refused
    assert "not routed to a team" in dispatch.refusal


async def test_a_routed_channel_dispatches_and_names_its_team() -> None:
    dispatcher = ChatDispatcher(bindings=Bindings(), routing=_routing())

    dispatch = await dispatcher.dispatch(_message(addressed=True))

    assert dispatch.action is SessionAction.START_INVESTIGATION
    assert not dispatch.refused
    assert dispatcher.team_for(THREAD) == "payments"


# --- Dispatch: authorisation ----------------------------------------------------


async def test_a_mapped_responder_may_start_an_investigation() -> None:
    dispatcher = ChatDispatcher(bindings=Bindings(), routing=_routing(), identities=_resolver())

    dispatch = await dispatcher.dispatch(_message(addressed=True))

    assert not dispatch.refused


async def test_an_unmapped_user_starting_a_run_is_refused_with_instructions() -> None:
    dispatcher = ChatDispatcher(bindings=Bindings(), routing=_routing(), identities=_resolver())

    dispatch = await dispatcher.dispatch(_message(addressed=True, user=STRANGER))

    assert dispatch.refused
    assert "U-nobody" in dispatch.refusal
    assert "Ask an operator" in dispatch.refusal


async def test_a_mapped_viewer_is_denied_rather_than_told_they_are_unmapped() -> None:
    dispatcher = ChatDispatcher(
        bindings=Bindings(), routing=_routing(), identities=_resolver(role=Role.VIEWER)
    )

    dispatch = await dispatcher.dispatch(_message(addressed=True))

    assert dispatch.refused
    assert "not mapped" not in dispatch.refusal


async def test_adding_mid_run_context_needs_the_same_permission_as_starting_one() -> None:
    """Guidance a run acts on is steering, so it is gated like starting."""
    bindings = Bindings()
    bindings.bind(THREAD, "run-1")
    dispatcher = ChatDispatcher(bindings=bindings, routing=_routing(), identities=_resolver())

    allowed = await dispatcher.dispatch(_message())
    refused = await dispatcher.dispatch(_message(user=STRANGER))

    assert allowed.action is SessionAction.ADD_CONTEXT
    assert not allowed.refused
    assert refused.refused


async def test_a_read_only_command_is_open_to_a_mapped_viewer() -> None:
    bindings = Bindings()
    bindings.bind(THREAD, "run-1")
    dispatcher = ChatDispatcher(
        bindings=bindings, routing=_routing(), identities=_resolver(role=Role.VIEWER)
    )

    dispatch = await dispatcher.dispatch(_message(command="status"))

    assert dispatch.action is SessionAction.RUN_COMMAND
    assert not dispatch.refused
    assert dispatch.command is not None
    assert dispatch.command.name == "status"


async def test_approving_from_chat_needs_the_approval_permission() -> None:
    bindings = Bindings()
    bindings.bind(THREAD, "run-1")
    dispatcher = ChatDispatcher(
        bindings=bindings, routing=_routing(), identities=_resolver(role=Role.VIEWER)
    )

    dispatch = await dispatcher.dispatch(_message(command="approve"))

    assert dispatch.refused


async def test_a_dispatcher_with_no_directory_authorises_nothing_and_refuses_nothing() -> None:
    """A deployment that has not configured identities is not a deployment that denies."""
    dispatcher = ChatDispatcher(bindings=Bindings())

    dispatch = await dispatcher.dispatch(_message(addressed=True, user=STRANGER))

    assert not dispatch.refused


async def test_an_ignored_message_is_never_authorised_or_refused() -> None:
    dispatcher = ChatDispatcher(bindings=Bindings(), routing=_routing(), identities=_resolver())

    dispatch = await dispatcher.dispatch(_message(user=STRANGER))

    assert dispatch.action is SessionAction.IGNORE
    assert not dispatch.refused


async def test_a_dispatched_message_in_a_bound_thread_carries_its_run() -> None:
    bindings = Bindings()
    bindings.bind(THREAD, "run-1")
    dispatcher = ChatDispatcher(bindings=bindings, routing=_routing())

    dispatch = await dispatcher.dispatch(_message())

    assert dispatch.run_id == "run-1"
