"""The four adapters, each driven by one recording transport.

The whole point of the shared contract is that a behaviour is asserted once and
run four times, so this file holds everything the four have in common: a fake
transport that records calls and can be told to fail, the fixtures that build
each adapter on top of one, and the parameterisation the suite reads.

The fake answers whatever the real platform answers for a successful post,
because the adapters parse those replies for a message id. Answering with a
generic ``{"ok": true}`` would let an adapter that never read the id pass.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from config.constants.surfaces import (
    CHAT_PLATFORM_DISCORD,
    CHAT_PLATFORM_MICROSOFT_TEAMS,
    CHAT_PLATFORM_SLACK,
    CHAT_PLATFORM_TELEGRAM,
)
from core.agent.interaction.models import ApprovalInteraction, InteractionKind, Question
from gateway.chat.port import (
    ChatPlatform,
    ChatRateLimited,
    ChatTarget,
    ChatUnavailable,
    PlatformCall,
    PlatformReply,
)
from gateway.discord.output_sink import DiscordPlatform
from gateway.slack.output_sink import SlackPlatform
from gateway.teams.stream_handler import TeamsPlatform
from gateway.telegram.output_sink import TelegramPlatform

BOT_USER_ID = "UBOT"
WORKSPACE = "W1"
CHANNEL = "C-incidents"
THREAD = "1700000000.000100"


@dataclass(slots=True)
class RecordingTransport:
    """Records every call, and answers the way the platform being faked does.

    ``fail_with`` is how the disconnect and rate-limit behaviours are driven: a
    transport that cannot be made to fail is one the resilience assertions
    cannot reach.
    """

    platform: str
    calls: list[PlatformCall] = field(default_factory=list)
    #: Raised instead of answering, once per entry, oldest first.
    failures: list[BaseException] = field(default_factory=list)
    #: Overrides the canned reply for a path, keyed by the path's last segment.
    replies: dict[str, PlatformReply] = field(default_factory=dict)
    counter: int = 0

    async def send(self, call: PlatformCall) -> PlatformReply:
        """Return the canned answer for ``call``, or raise the next queued failure."""
        self.calls.append(call)
        if self.failures:
            raise self.failures.pop(0)
        self.counter += 1
        segment = call.path.rstrip("/").rpartition("/")[2]
        if segment in self.replies:
            return self.replies[segment]
        return PlatformReply(status=200, document=self._document())

    def _document(self) -> Mapping[str, Any]:
        """Return the shape this platform answers a successful post with."""
        made = f"m{self.counter}"
        if self.platform == CHAT_PLATFORM_SLACK:
            return {"ok": True, "ts": made, "channel": CHANNEL}
        if self.platform == CHAT_PLATFORM_TELEGRAM:
            return {"ok": True, "result": {"message_id": self.counter, "chat": {"id": CHANNEL}}}
        if self.platform == CHAT_PLATFORM_DISCORD:
            return {"id": made, "channel_id": CHANNEL}
        return {"id": made}

    @property
    def paths(self) -> tuple[str, ...]:
        """Return every path called, in order."""
        return tuple(call.path for call in self.calls)

    def texts(self) -> tuple[str, ...]:
        """Return every piece of message text this transport was asked to deliver."""
        return tuple(_text_of(call.payload) for call in self.calls if _text_of(call.payload))


def _text_of(payload: Mapping[str, Any]) -> str:
    """Return whichever field this platform carries message text in."""
    for name in ("text", "content", "caption"):
        found = payload.get(name)
        if isinstance(found, str) and found:
            return found
    # Teams sends an activity; a card-only activity carries its text in the card.
    attachments = payload.get("attachments")
    if isinstance(attachments, list) and attachments:
        return _card_text(attachments[0])
    return ""


def _card_text(attachment: Any) -> str:
    """Return every text run of an Adaptive Card, joined."""
    if not isinstance(attachment, Mapping):
        return ""
    content = attachment.get("content")
    if not isinstance(content, Mapping):
        return ""
    return "\n".join(_runs(content))


def _runs(node: Any) -> list[str]:
    """Return every ``text`` value anywhere inside an Adaptive Card body."""
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in {"text", "title", "value"} and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_runs(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_runs(item))
    return found


#: How each adapter is built, and how a mention arrives on it. One row per
#: platform, so adding a fifth means adding a row rather than editing ten tests.
@dataclass(frozen=True, slots=True)
class Adapter:
    """One platform under test, with the payloads that platform actually sends."""

    platform: str
    build: Callable[[RecordingTransport], ChatPlatform]
    mention: Callable[[], Mapping[str, Any]]
    plain_message: Callable[[], Mapping[str, Any]]
    command: Callable[[], Mapping[str, Any]]
    decision: Callable[[str, str], Mapping[str, Any]]


def _slack_mention() -> Mapping[str, Any]:
    return {
        "type": "event_callback",
        "team_id": WORKSPACE,
        "event": {
            "type": "app_mention",
            "user": "U-ada",
            "text": f"<@{BOT_USER_ID}> what is happening with checkout?",
            "channel": CHANNEL,
            "ts": THREAD,
        },
    }


def _slack_plain() -> Mapping[str, Any]:
    return {
        "type": "event_callback",
        "team_id": WORKSPACE,
        "event": {
            "type": "message",
            "user": "U-ada",
            "text": "the deploy went out at 14:02",
            "channel": CHANNEL,
            "ts": "1700000000.000200",
            "thread_ts": THREAD,
        },
    }


def _slack_command() -> Mapping[str, Any]:
    return {
        "command": "/ninjasre",
        "text": "status",
        "team_id": WORKSPACE,
        "channel_id": CHANNEL,
        "user_id": "U-ada",
        "user_name": "ada",
    }


def _slack_decision(interaction_id: str, choice: str) -> Mapping[str, Any]:
    return {
        "type": "block_actions",
        "team": {"id": WORKSPACE},
        "user": {"id": "U-ada", "username": "ada"},
        "channel": {"id": CHANNEL},
        "message": {"thread_ts": THREAD, "ts": "1700000000.000300"},
        "actions": [{"action_id": f"ninjasre:{interaction_id}", "value": choice}],
    }


def _teams_mention() -> Mapping[str, Any]:
    return {
        "type": "message",
        "text": "<at>NinjaSRE</at> what is happening with checkout?",
        "id": "a-1",
        "conversation": {"id": f"{CHANNEL};messageid={THREAD}", "conversationType": "channel"},
        "from": {"id": "29:ada", "name": "Ada"},
        "channelData": {"tenant": {"id": WORKSPACE}},
        "entities": [{"type": "mention", "mentioned": {"id": BOT_USER_ID, "name": "NinjaSRE"}}],
    }


def _teams_plain() -> Mapping[str, Any]:
    return {
        "type": "message",
        "text": "the deploy went out at 14:02",
        "id": "a-2",
        "conversation": {"id": f"{CHANNEL};messageid={THREAD}", "conversationType": "channel"},
        "from": {"id": "29:ada", "name": "Ada"},
        "channelData": {"tenant": {"id": WORKSPACE}},
    }


def _teams_command() -> Mapping[str, Any]:
    return {
        "type": "message",
        "text": f"<at>NinjaSRE</at> {'/'}status",
        "id": "a-3",
        "conversation": {"id": f"{CHANNEL};messageid={THREAD}", "conversationType": "personal"},
        "from": {"id": "29:ada", "name": "Ada"},
        "channelData": {"tenant": {"id": WORKSPACE}},
        "entities": [{"type": "mention", "mentioned": {"id": BOT_USER_ID, "name": "NinjaSRE"}}],
    }


def _teams_decision(interaction_id: str, choice: str) -> Mapping[str, Any]:
    return {
        "type": "invoke",
        "name": "adaptiveCard/action",
        "id": "a-4",
        "conversation": {"id": f"{CHANNEL};messageid={THREAD}", "conversationType": "channel"},
        "from": {"id": "29:ada", "name": "Ada"},
        "channelData": {"tenant": {"id": WORKSPACE}},
        "replyToId": "card-1",
        "value": {"action": {"data": {"interaction_id": interaction_id, "choice": choice}}},
    }


def _telegram_mention() -> Mapping[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 11,
            "text": "@ninjasre_bot what is happening with checkout?",
            "chat": {"id": CHANNEL, "type": "supergroup"},
            "from": {"id": 4242, "username": "ada", "first_name": "Ada"},
            "entities": [{"type": "mention", "offset": 0, "length": 14}],
        },
    }


def _telegram_plain() -> Mapping[str, Any]:
    return {
        "update_id": 2,
        "message": {
            "message_id": 12,
            "text": "the deploy went out at 14:02",
            "chat": {"id": CHANNEL, "type": "supergroup"},
            "from": {"id": 4242, "username": "ada"},
            "reply_to_message": {"message_id": int(float(THREAD))},
            "message_thread_id": int(float(THREAD)),
        },
    }


def _telegram_command() -> Mapping[str, Any]:
    return {
        "update_id": 3,
        "message": {
            "message_id": 13,
            "text": "/status@ninjasre_bot",
            "chat": {"id": CHANNEL, "type": "supergroup"},
            "from": {"id": 4242, "username": "ada"},
            "entities": [{"type": "bot_command", "offset": 0, "length": 21}],
        },
    }


def _telegram_decision(interaction_id: str, choice: str) -> Mapping[str, Any]:
    return {
        "update_id": 4,
        "callback_query": {
            "id": "cb-1",
            "data": f"ninjasre:{interaction_id}:{choice}",
            "from": {"id": 4242, "username": "ada"},
            "message": {
                "message_id": 14,
                "chat": {"id": CHANNEL, "type": "supergroup"},
                "message_thread_id": int(float(THREAD)),
            },
        },
    }


def _discord_mention() -> Mapping[str, Any]:
    return {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": "9001",
            "content": f"<@{BOT_USER_ID}> what is happening with checkout?",
            "channel_id": CHANNEL,
            "guild_id": WORKSPACE,
            "author": {"id": "4242", "username": "ada", "bot": False},
            "mentions": [{"id": BOT_USER_ID}],
        },
    }


def _discord_plain() -> Mapping[str, Any]:
    return {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": "9002",
            "content": "the deploy went out at 14:02",
            "channel_id": THREAD,
            "guild_id": WORKSPACE,
            "author": {"id": "4242", "username": "ada", "bot": False},
            "thread": {"id": THREAD},
        },
    }


def _discord_command() -> Mapping[str, Any]:
    return {
        "t": "INTERACTION_CREATE",
        "d": {
            "id": "9003",
            "type": 2,
            "channel_id": CHANNEL,
            "guild_id": WORKSPACE,
            "member": {"user": {"id": "4242", "username": "ada"}},
            "data": {"name": "status", "options": []},
        },
    }


def _discord_decision(interaction_id: str, choice: str) -> Mapping[str, Any]:
    return {
        "t": "INTERACTION_CREATE",
        "d": {
            "id": "9004",
            "type": 3,
            "channel_id": THREAD,
            "guild_id": WORKSPACE,
            "message": {"id": "9005"},
            "member": {"user": {"id": "4242", "username": "ada"}},
            "data": {"custom_id": f"ninjasre:{interaction_id}:{choice}", "component_type": 2},
        },
    }


ADAPTERS: tuple[Adapter, ...] = (
    Adapter(
        platform=CHAT_PLATFORM_SLACK,
        build=lambda transport: SlackPlatform(transport=transport, bot_user_id=BOT_USER_ID),
        mention=_slack_mention,
        plain_message=_slack_plain,
        command=_slack_command,
        decision=_slack_decision,
    ),
    Adapter(
        platform=CHAT_PLATFORM_MICROSOFT_TEAMS,
        build=lambda transport: TeamsPlatform(transport=transport, bot_id=BOT_USER_ID),
        mention=_teams_mention,
        plain_message=_teams_plain,
        command=_teams_command,
        decision=_teams_decision,
    ),
    Adapter(
        platform=CHAT_PLATFORM_TELEGRAM,
        build=lambda transport: TelegramPlatform(transport=transport, bot_username="ninjasre_bot"),
        mention=_telegram_mention,
        plain_message=_telegram_plain,
        command=_telegram_command,
        decision=_telegram_decision,
    ),
    Adapter(
        platform=CHAT_PLATFORM_DISCORD,
        build=lambda transport: DiscordPlatform(transport=transport, application_id=BOT_USER_ID),
        mention=_discord_mention,
        plain_message=_discord_plain,
        command=_discord_command,
        decision=_discord_decision,
    ),
)


@pytest.fixture(params=ADAPTERS, ids=lambda adapter: adapter.platform)
def adapter(request: pytest.FixtureRequest) -> Adapter:
    """Return one of the four adapters under test."""
    return request.param  # type: ignore[no-any-return]


@pytest.fixture
def transport(adapter: Adapter) -> RecordingTransport:
    """Return the recording transport this adapter is driven through."""
    return RecordingTransport(platform=adapter.platform)


@pytest.fixture
def platform(adapter: Adapter, transport: RecordingTransport) -> ChatPlatform:
    """Return the adapter, built on the recording transport."""
    return adapter.build(transport)


@pytest.fixture
def target(adapter: Adapter) -> ChatTarget:
    """Return the thread an investigation runs in on this platform."""
    return ChatTarget(
        platform=adapter.platform, channel_id=CHANNEL, thread_id=THREAD, workspace_id=WORKSPACE
    )


def rate_limited(platform_name: str, *, retry_after_seconds: float = 0.0) -> ChatRateLimited:
    """Return the failure a platform's rate limiter produces."""
    return ChatRateLimited(platform_name, retry_after_seconds=retry_after_seconds)


def unavailable(platform_name: str, reason: str = "socket closed") -> ChatUnavailable:
    """Return the failure a dropped connection produces."""
    return ChatUnavailable(platform_name, reason)


def an_approval(interaction_id: str = "i-1", run_id: str = "run-1") -> ApprovalInteraction:
    """Return the approval every platform has to render completely."""
    raised = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    return ApprovalInteraction(
        interaction_id=interaction_id,
        run_id=run_id,
        raised_at=raised,
        expires_at=raised + timedelta(minutes=30),
        kind=InteractionKind.APPROVAL,
        summary="roll back checkout to the previous release",
        action="rollback deployment/checkout",
        diff="- image: checkout:1.4.2\n+ image: checkout:1.4.1",
        blast_radius="checkout, and the two services that call it",
        rollback_plan="redeploy checkout:1.4.2 and re-run the smoke suite",
    )


def a_question(interaction_id: str = "q-1", run_id: str = "run-1") -> Question:
    """Return the question every platform has to render decidably."""
    raised = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    return Question(
        interaction_id=interaction_id,
        run_id=run_id,
        raised_at=raised,
        expires_at=raised + timedelta(minutes=30),
        kind=InteractionKind.QUESTION,
        summary="was the 14:02 deploy intentional?",
        text="was the 14:02 deploy intentional?",
        options=("yes", "no"),
        reason="it decides whether this is a rollback or a code fix",
    )


def payload_texts(calls: Sequence[PlatformCall]) -> str:
    """Return every piece of text in every call, joined, for a leak assertion."""
    return "\n".join(str(call.payload) for call in calls)


async def no_wait(_seconds: float) -> None:
    """Do not actually wait.

    Every backoff in the chat surface is injected precisely so a suite asserting
    that it *waits* does not have to sit through the waiting. A test that used
    the real ``asyncio.sleep`` here would spend half a minute per platform
    proving a doubling that is already asserted directly.
    """
