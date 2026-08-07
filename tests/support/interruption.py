"""Doing the tidying up when the process is told to stop, not asked.

An exception unwinds and a ``finally`` runs. A signal does neither: ``SIGTERM``'s
default disposition ends the process where it stands, which is what a CI
cancellation and a ``kill`` both send, and it is the one exit that leaves a
chaos fault applied or a cloud stack running.

The handler here does the tidying and then **raises** rather than re-sending the
signal with its default disposition restored. Three things follow, and all three
are why: the caller sees the interruption as an outcome it can record instead of
disappearing; the surrounding ``finally`` blocks still run; and a test can
deliver a genuine signal without ending the test session, which is the only way
this property gets asserted at all rather than being hoped for.

What this cannot cover is ``SIGKILL``, and nothing can. Both suites therefore
have a second, independent recovery — a label sweep on the cluster, a tag sweep
in the cloud account — that removes what a killed run left whoever left it.
"""

from __future__ import annotations

import signal
import types
from collections.abc import Callable, Iterator
from contextlib import contextmanager

#: The signals a long-running suite installs a handler for. ``SIGINT`` is a
#: person at a keyboard and ``SIGTERM`` is a scheduler; both mean "stop", and
#: neither means "stop without tidying up".
INTERRUPT_SIGNALS: tuple[signal.Signals, ...] = (signal.SIGINT, signal.SIGTERM)


class RunInterrupted(Exception):
    """A run was signalled, and stopped after undoing what it had done."""


@contextmanager
def on_interrupt(
    action: Callable[[], None],
    *,
    signals: tuple[signal.Signals, ...] = INTERRUPT_SIGNALS,
    what: str = "the run",
) -> Iterator[None]:
    """Run ``action`` if one of ``signals`` arrives, then raise ``RunInterrupted``.

    Handlers are restored on the way out, so a suite does not leave the next
    Ctrl-C swallowed by apparatus that has finished with it.

    Raises:
        RunInterrupted: a signal arrived and ``action`` has run.
    """
    previous: dict[signal.Signals, object] = {}

    def on_signal(number: int, frame: types.FrameType | None) -> None:
        action()
        raise RunInterrupted(
            f"{what} was interrupted by {signal.Signals(number).name} and undid what it had "
            f"done before stopping"
        )

    for number in signals:
        try:
            previous[number] = signal.signal(number, on_signal)
        except ValueError:
            # Not the main thread. The caller's own ``finally`` still covers
            # every exit that unwinds at all, which is every one but this.
            continue

    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)  # type: ignore[arg-type]


__all__ = ["INTERRUPT_SIGNALS", "RunInterrupted", "on_interrupt"]
