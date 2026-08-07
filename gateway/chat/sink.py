"""The chat surface: what a run writes to, and what a human decides on.

One object owns everything that crosses from a run into a channel: the progress
message, the report, the interactive elements, and the failures. That is the
placement the constitution's fourth article needs — redaction at the sink means
one code path produces the safe text for chat and the full detail for the log,
with no flag anybody can default wrongly.

**It is an ``InteractionSurface``.** ``present`` and ``closed`` are the shared
interaction contract, and implementing it here is what makes an approval decided
in the console close the button in Slack, and one decided in one channel close
it in the other. Every chat sink is called ``chat``, so an interaction addressed
to the chat surface reaches all of them.

**Nothing here raises into a run.** A platform that has gone away is recorded,
reported through the fallback sink, and left behind. An investigation that failed
because a chat workspace was unreachable would be an investigation made less
reliable by having a chat surface at all.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from config.constants.surfaces import CHAT_MAX_DELIVERY_ATTEMPTS, SURFACE_CHAT
from core.agent.interaction.closure import InteractionEvent
from core.agent.interaction.models import Interaction
from gateway.chat.chunking import deliver_report
from gateway.chat.port import (
    ChatError,
    ChatPlatform,
    ChatRateLimited,
    ChatTarget,
    ChatUnavailable,
    PostedMessage,
)
from gateway.chat.streaming import ProgressSnapshot, ProgressStream, RateLimitBackoff
from platform.guardrails.sinks import Sink, SinkGuard
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class FallbackSink(Protocol):
    """Where a report goes when the chat platform did not take it.

    A protocol, because what the fallback *is* — a notification sink, an email,
    a file on the host — is a deployment's configuration and the notification
    layer's decision. What matters here is that there is somewhere for a finished
    investigation to land when the channel it started in has gone.
    """

    async def deliver(self, target: ChatTarget, text: str) -> None:
        """Deliver ``text`` for ``target`` by whatever route is still working."""


@dataclass(slots=True)
class RecordingFallback:
    """The shipped fallback: keep it, and say so.

    Deliberately not "drop it and log". An operator reading a run that ended
    ``degraded`` needs the report itself, and a deployment with no notification
    sink configured still has to have somewhere for it to be.
    """

    reports: list[str] = field(default_factory=list)
    targets: list[ChatTarget] = field(default_factory=list)

    async def deliver(self, target: ChatTarget, text: str) -> None:
        """Keep ``text`` so the run's report is not lost with the channel."""
        self.targets.append(target)
        self.reports.append(text)
        logger.warning(
            "chat.report_held_by_fallback",
            platform=target.platform,
            channel_id=target.channel_id,
            characters=len(text),
        )


@dataclass(slots=True)
class ChatSink:
    """One channel, seen as the place a run writes and a human decides.

    Holds the guard rather than a pre-redacted string, so nothing upstream has
    to remember to redact and nothing downstream can forget to.
    """

    platform: ChatPlatform
    target: ChatTarget
    guard: SinkGuard
    fallback: FallbackSink | None = None
    max_attempts: int = CHAT_MAX_DELIVERY_ATTEMPTS
    #: Injected for the same reason ``ProgressStream``'s is: a backoff whose
    #: waiting cannot be substituted is a backoff the suite has to sit through.
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clock: Callable[[], float] = time.monotonic
    stream: ProgressStream = field(init=False)

    delivered: bool = field(default=False, init=False)
    last_failure_reason: str = field(default="", init=False)
    _presented: dict[str, PostedMessage] = field(default_factory=dict, init=False, repr=False)
    _closed: list[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.stream = ProgressStream(
            platform=self.platform,
            target=self.target,
            max_attempts=self.max_attempts,
            clock=self.clock,
            sleep=self.sleep,
        )

    # -- InteractionSurface ----------------------------------------------------

    @property
    def name(self) -> str:
        """Return the surface name an interaction addresses chat by."""
        return SURFACE_CHAT

    async def present(self, interaction: Interaction) -> None:
        """Show ``interaction`` in this channel as the platform's own control."""
        element = self.platform.render_interaction(interaction)
        posted = await self._try(lambda: self.platform.send_interaction(self.target, element))
        if posted is not None:
            self._presented[interaction.interaction_id] = posted

    async def closed(self, event: InteractionEvent) -> None:
        """Stop offering to answer, and say what the decision was.

        A closure this channel never showed still posts the outcome rather than
        returning silently: two channels saw the approval, one of them pressed
        the button, and the other one's readers are the people who need telling.
        """
        message = self._presented.pop(event.interaction_id, None)
        if message is not None:
            await self._try(lambda: self.platform.close_interaction(message, event))
        else:
            await self.say(_outcome_line(event))
        self._closed.append(event.interaction_id)

    @property
    def closed_interactions(self) -> tuple[str, ...]:
        """Return the interactions this channel has been told are decided."""
        return tuple(self._closed)

    # -- What a run writes ------------------------------------------------------

    async def progress_started(self, text: str) -> None:
        """Post the one message this run's progress is written into."""
        await self.stream.start(self.guard.render(text, sink=Sink.CHAT))

    async def progress(self, snapshot: ProgressSnapshot) -> None:
        """Record ``snapshot``, editing the progress message if it is time."""
        await self.stream.update(snapshot)

    async def say(self, text: str) -> PostedMessage | None:
        """Post one message, as this sink may show it."""
        safe = self.guard.render(text, sink=Sink.CHAT)
        return await self._try(lambda: self.platform.post(self.target, safe))

    async def report(self, text: str) -> None:
        """Deliver the finished report, retrying, then falling back rather than losing it.

        The retry is what "delivered on reconnect" means: a platform
        that dropped its socket mid-incident is usually back within seconds, and
        a report that went straight to the fallback would leave the thread — the
        place the people who care are looking — without the answer.
        """
        safe = self.guard.render(text, sink=Sink.CHAT)
        backoff = RateLimitBackoff()
        for attempt in range(1, self.max_attempts + 1):
            try:
                delivery = await deliver_report(self.platform, self.target, safe)
            except ChatRateLimited as limited:
                self.last_failure_reason = "rate_limited"
                await self.sleep(backoff.next_delay(limited.retry_after_seconds))
                continue
            except ChatError as failure:
                self.last_failure_reason = _reason_of(failure)
            else:
                if delivery.complete:
                    self.delivered = True
                    return
                self.last_failure_reason = delivery.reason or "unavailable"
            logger.info(
                "chat.report_delivery_retrying",
                platform=self.platform.name,
                attempt=attempt,
                reason=self.last_failure_reason,
            )
            await self.sleep(backoff.next_delay())
        await self._hand_to_fallback(safe)

    async def failed(self, error: BaseException) -> None:
        """Say that the run failed, in the words chat is allowed to be told.

        The type name and nothing else. The full detail goes to the log with the
        same platform and channel on it, so whoever debugs this can find both
        halves. No exception detail ever reaches a chat message.
        """
        logger.error(
            "chat.run_failed",
            platform=self.platform.name,
            channel_id=self.target.channel_id,
            detail=self.guard.render_failure(error, sink=Sink.CLI),
        )
        await self._try(
            lambda: self.platform.post(
                self.target, self.guard.render_failure(error, sink=Sink.CHAT)
            )
        )

    @property
    def degraded(self) -> bool:
        """Return whether this channel stopped taking what the run sent it."""
        return self.stream.degraded or bool(self.last_failure_reason and not self.delivered)

    # -- Absorbing a platform that has gone away --------------------------------

    async def _try[T](self, call: Callable[[], Awaitable[T]]) -> T | None:
        """Run ``call``, recording a chat failure instead of raising it into the run."""
        try:
            return await call()
        except ChatUnavailable as gone:
            self.last_failure_reason = gone.reason or "unavailable"
            logger.warning(
                "chat.delivery_failed",
                platform=self.platform.name,
                channel_id=self.target.channel_id,
                reason=self.last_failure_reason,
            )
            return None
        except ChatError as failure:
            self.last_failure_reason = _reason_of(failure)
            logger.warning(
                "chat.delivery_refused",
                platform=self.platform.name,
                channel_id=self.target.channel_id,
                reason=self.last_failure_reason,
            )
            return None

    async def _hand_to_fallback(self, text: str) -> None:
        """Give the report to the fallback sink, or record that there is none."""
        if self.fallback is None:
            logger.error(
                "chat.report_lost_no_fallback",
                platform=self.platform.name,
                channel_id=self.target.channel_id,
                reason=self.last_failure_reason or "unavailable",
            )
            return
        await self.fallback.deliver(self.target, text)


def _outcome_line(event: InteractionEvent) -> str:
    """Return the sentence a channel that did not show the control is told."""
    who = event.answered_by or "somebody"
    if event.state.value == "answered":
        return f"{event.summary} — decided by {who}: {event.answer_text or 'answered'}"
    return f"{event.summary} — closed ({event.state.value})"


def _reason_of(failure: ChatError) -> str:
    """Return the short reason a chat failure records."""
    reason = getattr(failure, "reason", "")
    return str(reason) if reason else type(failure).__name__


__all__ = [
    "ChatSink",
    "FallbackSink",
    "RecordingFallback",
]
