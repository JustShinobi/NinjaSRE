"""Thread history informs an investigation, as data and never as instructions.

The two properties worth asserting separately: what the guardrail engine does to
the text on the way in, and what the framing does to how it arrives. A history
that was filtered but delivered as a bare block of prose would still be an
injection surface — the filtering removes secrets, and the framing is what makes
the block evidence rather than a request.
"""

from __future__ import annotations

import re

import pytest

from config.constants.surfaces import CHAT_THREAD_HISTORY_LIMIT
from gateway.chat.history import (
    OBSERVED_CONTEXT_HEADER,
    ObservedThread,
    ThreadHistoryReader,
)
from gateway.chat.port import ChatTarget, ChatUnavailable, ThreadMessage
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import GuardrailAction, GuardrailRule, Ruleset

pytestmark = pytest.mark.unit


class _Thread:
    """A platform that answers with whatever the test put in the thread."""

    def __init__(self, messages: tuple[ThreadMessage, ...], *, gone: bool = False) -> None:
        self.messages = messages
        self.gone = gone
        self.asked_for = 0

    @property
    def name(self) -> str:
        return "slack"

    async def thread_history(self, target: ChatTarget, *, limit: int) -> tuple[ThreadMessage, ...]:
        self.asked_for = limit
        if self.gone:
            raise ChatUnavailable("slack", "channel_not_found")
        return self.messages


def _said(author: str, text: str, *, is_bot: bool = False) -> ThreadMessage:
    return ThreadMessage(author=author, text=text, posted_at="1700000000.0", is_bot=is_bot)


def _reader(platform: object, **overrides: object) -> ThreadHistoryReader:
    return ThreadHistoryReader(
        platform=platform,  # type: ignore[arg-type]
        engine=GuardrailEngine(),
        **overrides,  # type: ignore[arg-type]
    )


TARGET = ChatTarget(platform="slack", channel_id="C1", thread_id="T1")


# --- What arrives ---------------------------------------------------------------


async def test_a_thread_becomes_an_attributed_transcript() -> None:
    platform = _Thread(
        (_said("ada", "the load balancer is fine"), _said("grace", "deploy at 14:02"))
    )

    observed = await _reader(platform).read(TARGET)

    assert [message.text for message in observed.messages] == [
        "the load balancer is fine",
        "deploy at 14:02",
    ]
    assert "> ada: the load balancer is fine" in observed.as_context()


async def test_the_transcript_says_what_it_is_before_it_says_anything_else() -> None:
    platform = _Thread((_said("ada", "the load balancer is fine"),))

    context = (await _reader(platform).read(TARGET)).as_context()

    assert context.startswith(OBSERVED_CONTEXT_HEADER)
    assert "not an instruction" in OBSERVED_CONTEXT_HEADER


async def test_an_empty_thread_contributes_nothing_rather_than_an_empty_header() -> None:
    observed = await _reader(_Thread(())).read(TARGET)

    assert observed.is_empty
    assert observed.as_context() == ""


async def test_the_bots_own_messages_are_left_out() -> None:
    platform = _Thread(
        (_said("ninjasre", "investigating…", is_bot=True), _said("ada", "any luck?"))
    )

    observed = await _reader(platform).read(TARGET)

    assert [message.author for message in observed.messages] == ["ada"]


async def test_the_bots_own_messages_can_be_included_where_a_deployment_wants_them() -> None:
    platform = _Thread(
        (_said("ninjasre", "investigating…", is_bot=True), _said("ada", "any luck?"))
    )

    observed = await _reader(platform, include_bot_messages=True).read(TARGET)

    assert len(observed.messages) == 2


# --- The guardrail engine is on the way in --------------------------------------


async def test_a_secret_in_the_thread_is_redacted_before_it_enters_context() -> None:
    ruleset = Ruleset(
        rules=(
            GuardrailRule(
                name="test-secret",
                patterns=(re.compile(r"sk-[A-Za-z0-9]{10,}"),),
                action=GuardrailAction.REDACT,
                replacement="[REDACTED]",
            ),
        )
    )
    platform = _Thread((_said("ada", "the key is sk-abcdefghijklmno"),))
    reader = ThreadHistoryReader(platform=platform, engine=GuardrailEngine(ruleset=ruleset))  # type: ignore[arg-type]

    observed = await reader.read(TARGET)

    assert "sk-abcdefghijklmno" not in observed.as_context()
    assert "[REDACTED]" in observed.messages[0].text
    assert observed.messages[0].redacted_by == ("test-secret",)


async def test_a_blocked_message_is_dropped_and_counted_rather_than_silently_absent() -> None:
    ruleset = Ruleset(
        rules=(
            GuardrailRule(
                name="test-block",
                patterns=(re.compile(r"forbidden"),),
                action=GuardrailAction.BLOCK,
                replacement="[BLOCKED]",
            ),
        )
    )
    platform = _Thread((_said("ada", "forbidden content"), _said("grace", "the deploy at 14:02")))
    reader = ThreadHistoryReader(platform=platform, engine=GuardrailEngine(ruleset=ruleset))  # type: ignore[arg-type]

    observed = await reader.read(TARGET)

    assert [message.author for message in observed.messages] == ["grace"]
    assert observed.blocked == 1
    assert "withheld by a guardrail rule" in observed.as_context()
    assert observed.rules_fired == ("test-block",)


# --- The bounds -----------------------------------------------------------------


async def test_the_message_count_is_bounded_and_the_newest_survive() -> None:
    platform = _Thread(tuple(_said("ada", f"message {index}") for index in range(10)))

    observed = await _reader(platform, limit=3).read(TARGET)

    assert [message.text for message in observed.messages] == [
        "message 7",
        "message 8",
        "message 9",
    ]
    assert observed.truncated is True
    assert "older messages omitted" in observed.as_context()


async def test_the_character_budget_is_bounded_and_the_newest_survive() -> None:
    platform = _Thread(tuple(_said("ada", "x" * 100) for _ in range(10)))

    observed = await _reader(platform, max_chars=250).read(TARGET)

    assert len(observed.messages) == 2
    assert observed.truncated is True


async def test_the_platform_is_asked_for_no_more_than_the_configured_limit() -> None:
    platform = _Thread(())

    await _reader(platform).read(TARGET)

    assert platform.asked_for == CHAT_THREAD_HISTORY_LIMIT


# --- History is an improvement, never a precondition ----------------------------


async def test_a_platform_that_cannot_be_reached_yields_an_empty_thread() -> None:
    observed = await _reader(_Thread((), gone=True)).read(TARGET)

    assert observed.is_empty
    assert observed.unavailable is True


def test_filtering_is_usable_without_a_platform_at_all() -> None:
    reader = ThreadHistoryReader(platform=None, engine=GuardrailEngine())  # type: ignore[arg-type]

    observed = reader.filter([_said("ada", "the deploy at 14:02")])

    assert isinstance(observed, ObservedThread)
    assert observed.messages[0].text == "the deploy at 14:02"
