"""Two ways in that behave the same, and one introduction per channel.

The claim worth asserting about the two ingress modes is that they *converge*:
the same handler sees the same payload whichever one delivered it. A second
parsing path is the way a mention starts working over HTTP and stops working
over Socket Mode without anybody noticing until an incident.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from gateway.chat.port import ChatUnavailable, PlatformCall, PlatformReply
from gateway.slack.intro import MAX_GREETED_CHANNELS, ChannelIntroducer, introduction
from gateway.slack.output_sink import SlackPlatform
from gateway.slack.socket_mode import (
    URL_VERIFICATION,
    SlackIngress,
    SlackIngressMode,
)

pytestmark = pytest.mark.unit

BOT = "UBOT"


class _Transport:
    """Records calls, and can be told to refuse."""

    def __init__(self, *, url: str = "wss://slack.example/link", fail: bool = False) -> None:
        self.calls: list[PlatformCall] = []
        self.url = url
        self.fail = fail

    async def send(self, call: PlatformCall) -> PlatformReply:
        self.calls.append(call)
        if self.fail:
            raise ChatUnavailable("slack", "channel_not_found")
        if call.path == "apps.connections.open":
            return PlatformReply(status=200, document={"ok": True, "url": self.url})
        return PlatformReply(status=200, document={"ok": True, "ts": "1700.1"})


def _mention(channel: str = "C1") -> Mapping[str, Any]:
    return {
        "type": "event_callback",
        "team_id": "W1",
        "event": {
            "type": "app_mention",
            "user": "U-ada",
            "text": f"<@{BOT}> what is happening?",
            "channel": channel,
            "ts": "1700.1",
        },
    }


class _Handler:
    def __init__(self, *, fail: bool = False) -> None:
        self.seen: list[Mapping[str, Any]] = []
        self.fail = fail

    async def __call__(self, payload: Mapping[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("handler exploded")
        self.seen.append(payload)


# --- The two modes converge ------------------------------------------------------


async def test_the_same_payload_reaches_the_handler_over_either_transport() -> None:
    over_socket, over_http = _Handler(), _Handler()
    socket = SlackIngress(handler=over_socket, mode=SlackIngressMode.SOCKET_MODE)
    http = SlackIngress(handler=over_http, mode=SlackIngressMode.HTTP_EVENTS)

    await socket.receive_envelope(
        {"type": "events_api", "envelope_id": "e-1", "payload": _mention()}
    )
    await http.receive_http(_mention())

    assert over_socket.seen == over_http.seen


def test_a_deployment_chooses_its_mode_by_configuration() -> None:
    assert (
        SlackIngress.configured(_Handler(), mode="socket_mode").mode is SlackIngressMode.SOCKET_MODE
    )
    assert (
        SlackIngress.configured(_Handler(), mode="http_events").mode is SlackIngressMode.HTTP_EVENTS
    )


def test_an_unknown_mode_is_refused_naming_the_two_that_exist() -> None:
    with pytest.raises(ValueError, match="socket_mode"):
        SlackIngress.configured(_Handler(), mode="carrier-pigeon")


# --- Socket Mode -----------------------------------------------------------------


async def test_an_envelope_is_acknowledged_by_its_own_id() -> None:
    ingress = SlackIngress(handler=_Handler())

    acknowledgement = await ingress.receive_envelope(
        {"type": "events_api", "envelope_id": "e-7", "payload": _mention()}
    )

    assert acknowledgement.envelope_id == "e-7"
    assert not acknowledgement.is_empty


async def test_an_unfamiliar_envelope_type_is_acknowledged_and_not_handled() -> None:
    """Slack adds envelope types; a gateway that crashed on one would stop delivering."""
    handler = _Handler()
    ingress = SlackIngress(handler=handler)

    acknowledgement = await ingress.receive_envelope(
        {"type": "hello", "envelope_id": "e-1", "payload": _mention()}
    )

    assert acknowledgement.envelope_id == "e-1"
    assert handler.seen == []


async def test_one_failing_handler_does_not_stop_the_socket() -> None:
    ingress = SlackIngress(handler=_Handler(fail=True))

    acknowledgement = await ingress.receive_envelope(
        {"type": "events_api", "envelope_id": "e-1", "payload": _mention()}
    )

    assert acknowledgement.envelope_id == "e-1"
    assert ingress.handled == 0


async def test_socket_mode_opens_a_connection_url() -> None:
    transport = _Transport()
    ingress = SlackIngress.configured(_Handler(), mode="socket_mode", api=_api(transport))

    assert await ingress.connection_url() == "wss://slack.example/link"


async def test_an_http_deployment_has_no_socket_to_open() -> None:
    ingress = SlackIngress.configured(_Handler(), mode="http_events")

    with pytest.raises(ChatUnavailable, match="over HTTP"):
        await ingress.connection_url()


async def test_socket_mode_without_a_client_says_so_rather_than_failing_obscurely() -> None:
    ingress = SlackIngress.configured(_Handler(), mode="socket_mode")

    with pytest.raises(ChatUnavailable, match="needs an API client"):
        await ingress.connection_url()


# --- HTTP events ------------------------------------------------------------------


async def test_a_url_verification_answers_the_challenge_and_handles_nothing() -> None:
    handler = _Handler()
    ingress = SlackIngress(handler=handler, mode=SlackIngressMode.HTTP_EVENTS)

    acknowledgement = await ingress.receive_http({"type": URL_VERIFICATION, "challenge": "abc123"})

    assert acknowledgement.body == {"challenge": "abc123"}
    assert handler.seen == []


async def test_an_event_is_handled_and_answered_ok() -> None:
    handler = _Handler()
    ingress = SlackIngress(handler=handler, mode=SlackIngressMode.HTTP_EVENTS)

    acknowledgement = await ingress.receive_http(_mention())

    assert acknowledgement.body == {"ok": True}
    assert len(handler.seen) == 1
    assert ingress.handled == 1


# --- The channel introduction ------------------------------------------------------


def _api(transport: _Transport) -> Any:
    from gateway.slack.client import SlackApi

    return SlackApi(transport=transport)  # type: ignore[arg-type]


def _joined(channel: str = "C1", *, user: str = BOT) -> Mapping[str, Any]:
    return {
        "type": "event_callback",
        "team_id": "W1",
        "event": {"type": "member_joined_channel", "user": user, "channel": channel},
    }


def test_the_introduction_explains_the_three_behaviours_people_discover_by_accident() -> None:
    text = introduction(BOT)

    assert f"<@{BOT}>" in text
    assert "thread" in text
    assert "no need to tag" in text
    assert "approval" in text
    assert "mapped to your Slack" in text


async def test_joining_a_channel_posts_the_introduction_once() -> None:
    transport = _Transport()
    greeter = ChannelIntroducer(
        platform=SlackPlatform(transport=transport, bot_user_id=BOT), bot_user_id=BOT
    )

    assert await greeter.handle(_joined()) is True
    assert await greeter.handle(_joined()) is False
    assert len(transport.calls) == 1
    assert greeter.greeted == ("C1",)


async def test_somebody_else_joining_is_not_this_bot_joining() -> None:
    transport = _Transport()
    greeter = ChannelIntroducer(
        platform=SlackPlatform(transport=transport, bot_user_id=BOT), bot_user_id=BOT
    )

    assert await greeter.handle(_joined(user="U-ada")) is False
    assert transport.calls == []


async def test_a_message_that_is_not_a_join_is_not_greeted() -> None:
    transport = _Transport()
    greeter = ChannelIntroducer(
        platform=SlackPlatform(transport=transport, bot_user_id=BOT), bot_user_id=BOT
    )

    assert await greeter.handle(_mention()) is False


async def test_a_failed_introduction_is_retried_on_the_next_join() -> None:
    """Otherwise the one channel where the intro mattered never gets it."""
    transport = _Transport(fail=True)
    greeter = ChannelIntroducer(
        platform=SlackPlatform(transport=transport, bot_user_id=BOT), bot_user_id=BOT
    )

    assert await greeter.handle(_joined()) is False
    assert greeter.greeted == ()

    transport.fail = False
    assert await greeter.handle(_joined()) is True


async def test_the_greeted_set_is_bounded() -> None:
    transport = _Transport()
    greeter = ChannelIntroducer(
        platform=SlackPlatform(transport=transport, bot_user_id=BOT), bot_user_id=BOT
    )

    for index in range(MAX_GREETED_CHANNELS + 1):
        await greeter.handle(_joined(f"C{index}"))

    assert len(greeter.greeted) <= MAX_GREETED_CHANNELS
