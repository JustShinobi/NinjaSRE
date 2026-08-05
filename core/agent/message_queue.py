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
not a channel for changing what the agent is allowed to do.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from config.constants.investigation import MESSAGE_QUEUE_DEBOUNCE_MS
from config.prompts.investigation import QUEUED_GUIDANCE_BLOCK

#: Injected so a test can assert the debounce without spending it.
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class QueuedMessage:
    """One piece of input a person supplied while the run was in progress."""

    text: str
    received_at: float
    author: str = ""

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("a queued message must carry text")


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
    _pending: list[QueuedMessage] = field(default_factory=list, repr=False)
    _last_received: float = field(default=0.0, repr=False)

    def submit(self, text: str, *, author: str = "") -> QueuedMessage:
        """Queue one message and return the record of it."""
        received = self.clock()
        message = QueuedMessage(text=text, received_at=received, author=author)
        self._pending.append(message)
        self._last_received = received
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
            if remaining <= 0:
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


__all__ = [
    "MessageQueue",
    "QueuedMessage",
    "Sleeper",
    "merge",
]
