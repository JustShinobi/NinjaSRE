"""Rendering a window of a long list instead of all of it.

A real investigation produces thousands of events, and a console that stalls
while rendering them stalls during the incident it was opened for. So a
transcript renders a window: the events around wherever the reader is, plus a
margin either side, and two spacers standing in for everything outside it so the
scrollbar still means what it looks like it means.

The property that matters is that the *rendered* size does not grow with the
transcript. Ten events and ten thousand produce the same number of elements, so
the cost of opening a run is independent of how long the run was — which is what
SC-001 asserts, at ten thousand.

The window is computed here rather than in the transcript renderer because it is
arithmetic with edge cases (an anchor near either end, a window larger than the
list, an empty list) and those are worth testing without a page around them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

#: How many events are rendered around the reader's position. Enough to fill a
#: tall screen twice over, so an ordinary scroll never reaches the edge of the
#: window before the next one is computed.
DEFAULT_WINDOW_SIZE: Final = 120

#: Extra rows rendered on each side of the window. The margin absorbs a fast
#: scroll: without one, the reader sees the spacer before the next window
#: arrives, which reads as the transcript having a hole in it.
DEFAULT_OVERSCAN: Final = 20


@dataclass(frozen=True, slots=True)
class Window:
    """Which slice of a long list is actually rendered, and what is outside it."""

    start: int
    count: int
    total: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.count < 0 or self.total < 0:
            raise ValueError("a window has no negative bound")
        if self.start + self.count > self.total:
            raise ValueError(
                f"a window of {self.count} from {self.start} runs past a list of {self.total}"
            )

    @property
    def stop(self) -> int:
        """Return the index one past the last rendered item."""
        return self.start + self.count

    @property
    def before(self) -> int:
        """Return how many items precede the window."""
        return self.start

    @property
    def after(self) -> int:
        """Return how many items follow the window."""
        return self.total - self.stop

    @property
    def is_whole(self) -> bool:
        """Return whether the window is the entire list, so no spacer is needed."""
        return self.count == self.total

    def contains(self, index: int) -> bool:
        """Return whether ``index`` is rendered."""
        return self.start <= index < self.stop


def window_of(
    total: int,
    *,
    anchor: int = 0,
    size: int = DEFAULT_WINDOW_SIZE,
    overscan: int = DEFAULT_OVERSCAN,
) -> Window:
    """Return the window to render for a list of ``total`` items around ``anchor``.

    ``anchor`` is the first item the reader is looking at. The window is placed
    to contain it with ``overscan`` items of margin, clamped so it never runs
    past either end — a window that hung off the end would render fewer rows at
    the bottom of a transcript than at the top, which reads as the list running
    out early.
    """
    if total <= 0:
        return Window(start=0, count=0, total=max(total, 0))

    span = min(max(size, 1) + 2 * max(overscan, 0), total)
    clamped_anchor = min(max(anchor, 0), total - 1)
    start = min(max(clamped_anchor - max(overscan, 0), 0), total - span)
    return Window(start=start, count=span, total=total)


def window_at_end(
    total: int, *, size: int = DEFAULT_WINDOW_SIZE, overscan: int = DEFAULT_OVERSCAN
) -> Window:
    """Return the window showing the end of the list.

    Where a live run is watched from: the newest event is the one that matters,
    and a stream that appended to the top of a window nobody was looking at
    would be a stream nobody could follow.
    """
    return window_of(total, anchor=max(total - 1, 0), size=size, overscan=overscan)


def slice_of[T](items: Sequence[T], window: Window) -> Sequence[T]:
    """Return the items ``window`` selects."""
    return items[window.start : window.stop]


__all__ = [
    "DEFAULT_OVERSCAN",
    "DEFAULT_WINDOW_SIZE",
    "Window",
    "slice_of",
    "window_at_end",
    "window_of",
]
