"""Letting someone add context to a run that is already going.

An operator watching an investigation knows things the agent does not, and the
moment they realise it is halfway through a turn. Two designs are wrong here.
Interrupting the turn discards work that is already in flight; waiting for the
run to finish delivers the guidance after it stopped mattering.

So input is queued, debounced, and merged at the next turn boundary as one
numbered block. The debounce is the part that is easy to skip and matters most:
somebody typing three sentences in three messages meant one instruction, and
delivering them as three separate interruptions makes the model treat the last
one as a correction of the first two.

The queue holds text only. It carries no authority: guidance is direction for
the investigation, and the block says so, because content arriving mid-run is
not a channel for changing what the agent is allowed to do. Two things follow
from that and are enforced here rather than trusted:

**Queued text is screened like any other human input.** Somebody pasting a
stack trace into an incident channel at three in the morning is pasting whatever
was in it, and the transcript is persisted.

**A merge emits a receipt.** Somebody who typed into a channel and saw nothing
happen types it again, and then a third time, and the run receives one
instruction three times with no way to tell that from three instructions.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.investigation import (
    MESSAGE_QUEUE_DEBOUNCE_FLOOR_SECONDS,
    MESSAGE_QUEUE_DEBOUNCE_MS,
)
from config.prompts.investigation import QUEUED_GUIDANCE_BLOCK
from core.agent.interaction.models import ContentFilter, screen_with
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Injected so a test can assert the debounce without spending it.
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class QueuedMessage:
    """One piece of input a person supplied while the run was in progress.

    ``surface`` is where it came from, and it is carried rather than dropped so
    the receipt goes back to the place the person is looking at. Somebody who
    typed in Slack and got their acknowledgement in the console has, from where
    they are sitting, been ignored.
    """

    text: str
    received_at: float
    author: str = ""
    surface: str = ""
    #: Guardrail rules that rewrote this on the way in. Kept so a reviewer can
    #: see that what the model read is not what somebody typed.
    redacted_by: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("a queued message must carry text")

    @property
    def redacted(self) -> bool:
        """Return whether the guardrails altered this message."""
        return bool(self.redacted_by)


def merge(messages: Sequence[QueuedMessage]) -> str:
    """Return the numbered guidance block ``messages`` become.

    Numbered even when there is one, so the model reads a list rather than a
    sentence that might be a new task. The framing is in
    ``QUEUED_GUIDANCE_BLOCK`` and says explicitly that this is direction rather
    than a fresh objective.
    """
    items = "\n".join(
        f"{index}. {message.text.strip()}" for index, message in enumerate(messages, start=1)
    )
    return QUEUED_GUIDANCE_BLOCK.format(items=items)


@dataclass(frozen=True, slots=True)
class MergeReceipt:
    """What a surface is told when the guidance somebody typed reached the run.

    Sent on the merge rather than on the submit, because the two answer
    different questions. "We have it" is true the moment it is queued and is not
    what somebody wants to know; "the agent has read it" is only true at the
    turn boundary, and it is the one that stops them from typing it again.
    """

    run_id: str
    messages: int
    surfaces: tuple[str, ...] = ()
    authors: tuple[str, ...] = ()
    redacted: bool = False

    def describe(self) -> str:
        """Return the one line a surface shows."""
        plural = "" if self.messages == 1 else "s"
        note = " (redacted by the guardrails)" if self.redacted else ""
        return f"{self.messages} message{plural} added to the investigation{note}."

    def to_record(self) -> dict[str, Any]:
        """Return the stored form a transport serialises."""
        return {
            "run_id": self.run_id,
            "messages": self.messages,
            "surfaces": list(self.surfaces),
            "authors": list(self.authors),
            "redacted": self.redacted,
        }


@runtime_checkable
class ReceiptSink(Protocol):
    """Somewhere a merge receipt is delivered."""

    @property
    def name(self) -> str:
        """Return what this sink is called, for the log line when it fails."""

    async def acknowledge(self, receipt: MergeReceipt) -> None:
        """Tell whoever typed that the run has now read it."""


@dataclass(slots=True)
class MessageQueue:
    """Mid-run input, held until the next turn boundary.

    Not thread-safe and not shared: one queue belongs to one run. Two runs
    sharing a queue would deliver an operator's guidance to whichever
    investigation reached a boundary first.
    """

    debounce_ms: int = MESSAGE_QUEUE_DEBOUNCE_MS
    clock: Callable[[], float] = time.monotonic
    sleeper: Sleeper = asyncio.sleep
    screen: ContentFilter | None = None
    receipts: tuple[ReceiptSink, ...] = ()
    run_id: str = ""
    _pending: list[QueuedMessage] = field(default_factory=list, repr=False)
    _last_received: float = field(default=0.0, repr=False)

    def submit(self, text: str, *, author: str = "", surface: str = "") -> QueuedMessage:
        """Queue one message from any surface and return the record of it.

        Screened here rather than at the merge. A message sits in the queue for
        as long as somebody keeps typing, and a secret that spent that time
        unredacted in memory is a secret that was unredacted in a heap dump.
        """
        screened = screen_with(self.screen, text)
        received = self.clock()
        message = QueuedMessage(
            text=screened.text,
            received_at=received,
            author=author,
            surface=surface,
            redacted_by=screened.rules,
        )
        self._pending.append(message)
        self._last_received = received
        if screened.altered:
            logger.info(
                "agent.queued_message_redacted",
                run_id=self.run_id,
                surface=surface,
                rules=list(screened.rules),
            )
        return message

    @property
    def pending(self) -> int:
        """Return how many messages are waiting to be merged."""
        return len(self._pending)

    def __bool__(self) -> bool:
        """Return whether anything is waiting."""
        return bool(self._pending)

    async def drain(self) -> tuple[QueuedMessage, ...]:
        """Return everything queued, once the debounce window has gone quiet.

        Waits from the *last* message rather than the first: a burst that is
        still arriving is still one instruction, and taking the first half of it
        to the model is worse than waiting another second.
        """
        if not self._pending:
            return ()

        while True:
            quiet_for = self.clock() - self._last_received
            remaining = (self.debounce_ms / 1000.0) - quiet_for
            if remaining <= MESSAGE_QUEUE_DEBOUNCE_FLOOR_SECONDS:
                break
            await self.sleeper(remaining)

        drained = tuple(self._pending)
        self._pending.clear()
        return drained

    def drain_now(self) -> tuple[QueuedMessage, ...]:
        """Return everything queued without waiting out the debounce window.

        For the paths where waiting is wrong: a run that is ending, and a
        cancellation that should not be delayed by a debounce nobody is going to
        read the result of.
        """
        drained = tuple(self._pending)
        self._pending.clear()
        return drained

    async def acknowledge(self, drained: Sequence[QueuedMessage]) -> MergeReceipt:
        """Tell every receipt sink that ``drained`` reached the run, and return what.

        A sink that fails does not stop the others, and a failed receipt does
        not fail the merge: the guidance is already in the transcript, and
        undoing that because an acknowledgement did not send would throw away
        the thing that mattered to keep the thing that did not.
        """
        receipt = receipt_for(drained, run_id=self.run_id)
        for sink in self.receipts:
            try:
                await sink.acknowledge(receipt)
            except Exception as failure:  # noqa: BLE001 — one sink must not stop the rest
                logger.error(
                    "agent.merge_receipt_failed",
                    run_id=self.run_id,
                    sink=sink.name,
                    error=str(failure),
                )
        return receipt


def receipt_for(drained: Sequence[QueuedMessage], *, run_id: str) -> MergeReceipt:
    """Return the receipt ``drained`` produces."""
    return MergeReceipt(
        run_id=run_id,
        messages=len(drained),
        surfaces=tuple(dict.fromkeys(message.surface for message in drained if message.surface)),
        authors=tuple(dict.fromkeys(message.author for message in drained if message.author)),
        redacted=any(message.redacted for message in drained),
    )


__all__ = [
    "MergeReceipt",
    "MessageQueue",
    "QueuedMessage",
    "ReceiptSink",
    "Sleeper",
    "merge",
    "receipt_for",
]
