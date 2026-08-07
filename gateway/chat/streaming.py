"""One progress message, rewritten — never a message per event.

A busy incident channel is the environment this has to survive, and posting one
message per agent event makes the bot unusable there within a minute: the thread
becomes unreadable and the platform starts refusing calls. So a run posts
exactly one progress message and edits it, at a bounded interval, however many
events arrive in between.

**Coalescing is not dropping.** An update that arrives inside the interval
replaces the pending snapshot rather than being discarded — the *content* is
still delivered, at the next edit, and ``dropped`` stays zero. That distinction
is the whole point: a rate-limited update must not lose content, and the only
way to be sure is for nothing to have a discard path at all.

**A rate limit is waited out, not retried.** ``Retry-After`` from the platform
wins over the configured doubling, because a vendor that names a number knows
something the caller's backoff does not. After ``CHAT_MAX_DELIVERY_ATTEMPTS``
consecutive refusals the stream goes ``degraded`` and stops editing: the run
carries on unwatched rather than spending its time on a surface that is not
answering.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Final

from config.constants.surfaces import (
    CHAT_MAX_DELIVERY_ATTEMPTS,
    CHAT_RATE_LIMIT_BACKOFF_FACTOR,
    CHAT_RATE_LIMIT_BACKOFF_SECONDS,
    CHAT_RATE_LIMIT_MAX_BACKOFF_SECONDS,
    CHAT_STREAM_EDIT_INTERVAL_SECONDS,
)
from gateway.chat.port import (
    ChatPlatform,
    ChatRateLimited,
    ChatTarget,
    ChatUnavailable,
    PlatformLimits,
    PostedMessage,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: How many capability names a progress line lists before it says "and n more".
#: A progress message is read at a glance during an incident; a list of twenty
#: tool names is not read at all.
MAX_LISTED_CAPABILITIES: Final = 4


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    """Where a run has got to, as one line somebody reads mid-incident."""

    stage: str = ""
    capabilities: tuple[str, ...] = ()
    elapsed_seconds: float = 0.0
    note: str = ""

    def render(self) -> str:
        """Return the text the progress message shows for this snapshot."""
        parts = [self.stage or "investigating"]
        if self.capabilities:
            parts.append(f"· {self._capabilities()}")
        if self.elapsed_seconds:
            parts.append(f"· {self.elapsed_seconds:.0f}s")
        line = " ".join(parts)
        return f"{line}\n{self.note}" if self.note else line

    def _capabilities(self) -> str:
        """Return the capability list, bounded."""
        shown = self.capabilities[:MAX_LISTED_CAPABILITIES]
        remaining = len(self.capabilities) - len(shown)
        listed = ", ".join(shown)
        return f"{listed} and {remaining} more" if remaining > 0 else listed


def interval_for(limits: PlatformLimits) -> float:
    """Return how often ``limits``' platform may have one message rewritten.

    The wider of two bounds, and both are load-bearing. The configured interval
    is a *readability* floor — a message rewritten faster than this flickers and
    nobody can read a line of it. The platform's own budget is a *rate* floor,
    and it differs per platform: three seconds is twenty edits a minute, which
    Discord accepts and Slack does not.
    """
    return max(CHAT_STREAM_EDIT_INTERVAL_SECONDS, 60.0 / max(limits.edits_per_minute, 1))


@dataclass(slots=True)
class RateLimitBackoff:
    """The wait after a refusal, doubling to a ceiling, overridden by the platform."""

    seconds: float = CHAT_RATE_LIMIT_BACKOFF_SECONDS
    factor: float = CHAT_RATE_LIMIT_BACKOFF_FACTOR
    ceiling: float = CHAT_RATE_LIMIT_MAX_BACKOFF_SECONDS
    _current: float = field(default=0.0, init=False)

    def next_delay(self, retry_after_seconds: float = 0.0) -> float:
        """Return how long to wait, and advance the doubling.

        A platform-supplied ``Retry-After`` is returned unchanged and does not
        advance the doubling: it is an instruction, not an estimate, and letting
        it compound would turn a four-second wait into a minute.
        """
        if retry_after_seconds > 0:
            return retry_after_seconds
        self._current = (
            self.seconds if self._current == 0 else min(self._current * self.factor, self.ceiling)
        )
        return self._current

    def reset(self) -> None:
        """Forget the doubling, after a call the platform accepted."""
        self._current = 0.0


@dataclass(slots=True)
class ProgressStream:
    """The one message a run's progress is written into, and rewritten in.

    Holds the pending snapshot rather than a queue. A queue would be a list of
    stale progress lines nobody wants to read in order; the only interesting
    snapshot is the most recent one, and coalescing onto it is what makes a
    two-hundred-event run cost a handful of edits.
    """

    platform: ChatPlatform
    target: ChatTarget
    #: Computed from the platform's own edit budget unless a caller overrides
    #: it. A single global interval is not enough on its own: three seconds is
    #: twenty edits a minute, which is inside Discord's budget and past Slack's,
    #: and a two-hundred-event run is exactly where that difference bites.
    interval_seconds: float = 0.0
    max_attempts: int = CHAT_MAX_DELIVERY_ATTEMPTS
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    backoff: RateLimitBackoff = field(default_factory=RateLimitBackoff)

    message: PostedMessage | None = field(default=None, init=False)
    posts: int = field(default=0, init=False)
    edits: int = field(default=0, init=False)
    coalesced: int = field(default=0, init=False)
    #: Content that never reached the platform and never will. Asserted to stay
    #: zero: coalescing replaces a snapshot, it does not discard one.
    dropped: int = field(default=0, init=False)
    degraded: bool = field(default=False, init=False)
    last_failure_reason: str = field(default="", init=False)

    _pending: ProgressSnapshot | None = field(default=None, init=False, repr=False)
    _last_edit_at: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            self.interval_seconds = interval_for(self.platform.limits)

    @property
    def last_text(self) -> str | None:
        """Return what the progress message currently says, or ``None``."""
        return self.message.text if self.message else None

    async def start(self, text: str) -> PostedMessage | None:
        """Post the one message this run's progress will be written into.

        Returns ``None`` when the platform refused: a run whose progress message
        could not be posted still runs, and the report still has a fallback.
        """
        posted = await self._attempt(lambda: self.platform.post(self.target, text))
        if posted is None:
            return None
        self.message = posted
        self.posts += 1
        self._last_edit_at = self.clock()
        return posted

    async def update(self, snapshot: ProgressSnapshot) -> bool:
        """Record ``snapshot`` and edit the message if the interval has elapsed.

        Returns whether an edit was actually made. A ``False`` here is a
        coalesce, never a loss: the snapshot is held and goes out on the next
        edit or on ``flush``.
        """
        self._pending = snapshot
        if self.degraded or self.message is None:
            self.coalesced += 1
            return False
        if self.clock() - self._last_edit_at < self.interval_seconds:
            self.coalesced += 1
            return False
        return await self.flush()

    async def flush(self) -> bool:
        """Write the pending snapshot out now, whatever the interval says.

        What the end of a run calls, so the last thing the progress message says
        is where the run actually finished rather than wherever the last
        interval boundary happened to fall.
        """
        if self._pending is None or self.message is None or self.degraded:
            return False
        snapshot = self._pending
        edited = await self._attempt(lambda: self.platform.edit(self.message, snapshot.render()))  # type: ignore[arg-type]
        if edited is None:
            return False
        self.message = edited
        self._pending = None
        self.edits += 1
        self._last_edit_at = self.clock()
        return True

    async def _attempt(self, call: Callable[[], Awaitable[PostedMessage]]) -> PostedMessage | None:
        """Run ``call``, waiting out rate limits, and degrade rather than raise.

        Returns ``None`` once the attempt budget is spent. Nothing here re-raises
        into the run: chat is a surface, and a surface that could fail an
        investigation would make the investigation less reliable than not having
        it.
        """
        for attempt in range(1, self.max_attempts + 1):
            try:
                posted = await call()
            except ChatRateLimited as limited:
                delay = self.backoff.next_delay(limited.retry_after_seconds)
                self.last_failure_reason = "rate_limited"
                logger.info(
                    "chat.rate_limited",
                    platform=self.platform.name,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await self.sleep(delay)
            except ChatUnavailable as gone:
                self.last_failure_reason = gone.reason or "unavailable"
                logger.warning(
                    "chat.delivery_failed",
                    platform=self.platform.name,
                    attempt=attempt,
                    reason=self.last_failure_reason,
                )
                await self.sleep(self.backoff.next_delay())
            else:
                self.backoff.reset()
                return posted

        self.degraded = True
        logger.warning(
            "chat.stream_degraded",
            platform=self.platform.name,
            attempts=self.max_attempts,
            reason=self.last_failure_reason,
        )
        return None


__all__ = [
    "MAX_LISTED_CAPABILITIES",
    "ProgressSnapshot",
    "ProgressStream",
    "RateLimitBackoff",
    "interval_for",
]
