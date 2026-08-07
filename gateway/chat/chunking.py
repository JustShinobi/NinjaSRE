"""Delivering a report that is longer than the platform will accept.

Two ways to be complete, and the choice is made on how many *messages* splitting
would take rather than on the byte count. Fifteen messages is where a thread
stops being readable; past that an attachment keeps the whole report in one
addressable place that somebody can link to later. Both ways deliver every
character — the one thing this module must never do is truncate, because a
report that quietly lost its last section is worse than no report at all.

**Splitting breaks on structure where it can.** Paragraph, then line, then word,
then — for a base64 blob with no whitespace in it — the character. A split that
lands mid-sentence is ugly; a split that drops the tail is a defect, and the
fallback chain exists so the second never happens in service of avoiding the
first.

**Every part says which part it is.** ``[2/5]`` on each message, because chat
platforms reorder nothing but readers scroll, and "is this the end of the
report" has to be answerable from the message itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from config.constants.surfaces import CHAT_MAX_REPORT_CHUNKS
from gateway.chat.port import (
    Attachment,
    ChatPlatform,
    ChatTarget,
    ChatUnavailable,
    PlatformLimits,
    PostedMessage,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What a part marker costs, at the widest it gets. Reserved out of every chunk
#: so adding the marker cannot push a chunk back over the limit — computing the
#: marker after the split is how an off-by-one becomes a rejected message.
_MARKER_BUDGET = len("[999/999]\n")


def split_message(text: str, limit: int) -> tuple[str, ...]:
    """Return ``text`` cut into pieces of at most ``limit`` characters.

    Raises:
        ValueError: ``limit`` is not a length anything could fit in.
    """
    if limit <= 0:
        raise ValueError(f"a message limit of {limit} leaves no room for a message")
    if len(text) <= limit:
        return (text,)

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = _break_at(remaining, limit)
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return tuple(chunks)


def _break_at(text: str, limit: int) -> int:
    """Return where to cut ``text`` so the piece reads as something.

    Falls all the way through to ``limit`` itself: a run of ``limit`` characters
    with no separator in it is a base64 blob or a minified document, and cutting
    it mid-token is the only alternative to losing it.
    """
    window = text[:limit]
    for separator in ("\n\n", "\n", " "):
        found = window.rfind(separator)
        if found > 0:
            return found + len(separator)
    return limit


@dataclass(frozen=True, slots=True)
class ReportDelivery:
    """What actually reached the thread, and the proof nothing was lost."""

    chunks: tuple[str, ...] = ()
    messages: tuple[PostedMessage, ...] = ()
    attachment: Attachment | None = None
    #: The pieces that could not be posted at all — the platform went away
    #: mid-delivery. Non-empty means the caller has to reach for the fallback.
    undelivered: tuple[str, ...] = ()
    #: Why delivery stopped, in the platform's own words. Carried rather than
    #: only logged: the caller decides between retrying and falling back, and
    #: "the bot was removed from the channel" and "the API is down" are not the
    #: same decision.
    reason: str = ""
    _source: str = field(default="", repr=False)

    @property
    def complete(self) -> bool:
        """Return whether the whole report reached the thread."""
        if self.undelivered:
            return False
        return bool(self.attachment) or bool(self.messages)

    @property
    def recovered_text(self) -> str:
        """Return the report as a reader reassembling the parts would have it.

        Reads the delivered pieces rather than the source, so an assertion that
        nothing was lost is an assertion about what was *sent*.
        """
        if self.attachment is not None:
            return self.attachment.content
        return "".join(self.chunks)


async def deliver_report(
    platform: ChatPlatform,
    target: ChatTarget,
    text: str,
    *,
    limits: PlatformLimits | None = None,
    filename: str = "investigation-report.md",
    title: str = "Investigation report",
) -> ReportDelivery:
    """Post ``text`` to ``target``, splitting or attaching so nothing is lost.

    A platform that has no file upload falls back to splitting however many
    messages that takes: a long thread is a cost, and a missing conclusion is a
    defect.
    """
    bounds = limits or platform.limits
    chunks = split_message(text, max(bounds.message_limit - _MARKER_BUDGET, 1))

    if len(chunks) > CHAT_MAX_REPORT_CHUNKS and bounds.supports_attachments:
        return await _attach(platform, target, text, chunks, filename=filename, title=title)
    return await _post_parts(platform, target, chunks)


async def _post_parts(
    platform: ChatPlatform, target: ChatTarget, chunks: Sequence[str]
) -> ReportDelivery:
    """Post every part in order, stopping at the first the platform refused."""
    posted: list[PostedMessage] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        body = f"[{index}/{total}]\n{chunk}" if total > 1 else chunk
        try:
            posted.append(await platform.post(target, body))
        except ChatUnavailable as gone:
            logger.warning(
                "chat.report_part_undelivered",
                platform=platform.name,
                part=index,
                parts=total,
                reason=gone.reason,
            )
            return ReportDelivery(
                chunks=tuple(chunks),
                messages=tuple(posted),
                undelivered=tuple(chunks[index - 1 :]),
                reason=gone.reason or "unavailable",
                _source="".join(chunks),
            )
    return ReportDelivery(chunks=tuple(chunks), messages=tuple(posted), _source="".join(chunks))


async def _attach(
    platform: ChatPlatform,
    target: ChatTarget,
    text: str,
    chunks: Sequence[str],
    *,
    filename: str,
    title: str,
) -> ReportDelivery:
    """Deliver the report as a file, falling back to splitting if that fails.

    The thread still gets a message. A file on its own reads as an attachment
    somebody forgot to describe, and the first line of a root cause is the part
    people act on.
    """
    attachment = Attachment(filename=filename, content=text, title=title)
    try:
        posted = await platform.attach(target, attachment)
    except ChatUnavailable as gone:
        logger.info(
            "chat.attachment_refused_falling_back_to_split",
            platform=platform.name,
            reason=gone.reason,
        )
        return await _post_parts(platform, target, chunks)
    return ReportDelivery(
        chunks=tuple(chunks), messages=(posted,), attachment=attachment, _source=text
    )


__all__ = [
    "ReportDelivery",
    "deliver_report",
    "split_message",
]
