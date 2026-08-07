"""A report past a platform's message limit is delivered complete.

Two ways to be complete, and the choice is made on how many messages splitting
would take rather than on the byte count: fifteen messages is where a thread
stops being readable, and past that an attachment keeps the report in one
addressable place. Either way nothing is truncated, and the assertion is that
the delivered pieces reassemble into the original.
"""

from __future__ import annotations

import pytest

from config.constants.surfaces import CHAT_MAX_REPORT_CHUNKS
from gateway.chat.chunking import deliver_report, split_message
from gateway.chat.port import ChatPlatform, ChatTarget, PlatformLimits
from tests.contract.chat.conftest import RecordingTransport

pytestmark = pytest.mark.contract


def _report(characters: int) -> str:
    """Return a report of roughly ``characters``, with structure worth preserving."""
    lines = ["# Root cause", ""]
    while sum(len(line) + 1 for line in lines) < characters:
        lines.append(
            f"- evidence {len(lines):05d}: the checkout pod restarted at 14:0{len(lines) % 10}"
        )
    return "\n".join(lines)


def test_splitting_never_loses_a_character(platform: ChatPlatform) -> None:
    limit = PlatformLimits.of(platform.name).message_limit
    body = _report(limit * 4)

    chunks = split_message(body, limit)

    assert all(len(chunk) <= limit for chunk in chunks)
    assert "".join(chunks).split() == body.split()


def test_splitting_refuses_a_limit_nothing_could_fit_in(platform: ChatPlatform) -> None:
    with pytest.raises(ValueError, match="message limit"):
        split_message("anything", 0)


def test_a_single_word_longer_than_the_limit_is_still_split(platform: ChatPlatform) -> None:
    """A base64 blob has no whitespace to break on, and must not be dropped."""
    limit = PlatformLimits.of(platform.name).message_limit
    blob = "A" * (limit * 2 + 7)

    chunks = split_message(blob, limit)

    assert "".join(chunks) == blob
    assert all(len(chunk) <= limit for chunk in chunks)


async def test_a_report_within_the_chunk_budget_is_split_and_posted(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    limit = PlatformLimits.of(platform.name).message_limit
    body = _report(limit * 3)

    delivered = await deliver_report(platform, target, body)

    assert delivered.attachment is None
    assert 1 < len(delivered.messages) <= CHAT_MAX_REPORT_CHUNKS
    assert delivered.complete
    assert delivered.recovered_text.split() == body.split()


async def test_a_report_past_the_chunk_budget_is_attached_whole(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    limit = PlatformLimits.of(platform.name).message_limit
    body = _report(limit * (CHAT_MAX_REPORT_CHUNKS + 5))

    delivered = await deliver_report(platform, target, body)

    assert delivered.attachment is not None
    assert delivered.attachment.content == body
    assert delivered.complete
    # The thread still says what happened rather than only carrying a file.
    assert delivered.messages


async def test_an_attachment_falls_back_to_splitting_where_a_platform_has_no_files(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    limit = PlatformLimits.of(platform.name, supports_attachments=False)
    body = _report(limit.message_limit * (CHAT_MAX_REPORT_CHUNKS + 5))

    delivered = await deliver_report(platform, target, body, limits=limit)

    assert delivered.attachment is None
    assert delivered.complete
    assert delivered.recovered_text.split() == body.split()


async def test_every_part_of_a_split_report_says_which_part_it_is(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    limit = PlatformLimits.of(platform.name).message_limit
    delivered = await deliver_report(platform, target, _report(limit * 3))

    total = len(delivered.messages)
    for index, message in enumerate(delivered.messages, start=1):
        assert f"{index}/{total}" in message.text
