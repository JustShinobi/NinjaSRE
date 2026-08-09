"""Noticing that a model has asked for the same thing once too often.

The duplicate cache in the runtime already answers a repeated call from memory
and tells the model it is a repeat. That is the right thing to do per call and it
does not break anything out of anything: a model that has decided to re-read one
query will re-read it every iteration, each time being told politely that it
already has the result, until the iteration ceiling ends the run.

So repetition is counted across turns, inside a declared window, and at the
ceiling the model is told in a sentence that names the call and the count. The
window is short and the ceiling is low, both so that the break happens *while
there are iterations left to recover in*. Detecting this at the iteration
ceiling would be detecting it after it mattered.

The count is per session. A client is cached per role and shared by every run in
the process, so two investigations that happen to make the same call must not
add up to a repetition in either — which is why this holds a map keyed by
session rather than a single window.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field

from config.constants.llm import (
    MAX_IDENTICAL_CALLS_IN_WINDOW,
    MODEL_PROBE_CACHE_MAX_ENTRIES,
    REPEATED_CALL_WINDOW,
)
from core.llm.resilience.arguments import signature
from core.llm.types import ToolCall


@dataclass(frozen=True, slots=True)
class RepetitionVerdict:
    """Whether the model is stuck, and on what."""

    repeating: bool = False
    capability: str = ""
    count: int = 0
    window: int = REPEATED_CALL_WINDOW


@dataclass(slots=True)
class RepetitionDetector:
    """Counts identical calls per session inside a sliding window."""

    window: int = REPEATED_CALL_WINDOW
    ceiling: int = MAX_IDENTICAL_CALLS_IN_WINDOW
    max_sessions: int = MODEL_PROBE_CACHE_MAX_ENTRIES
    _recent: OrderedDict[str, deque[tuple[str, str]]] = field(
        default_factory=OrderedDict, repr=False
    )

    def __post_init__(self) -> None:
        if self.window < 1 or self.ceiling < 1:
            raise ValueError("the window and the ceiling must both be at least 1")

    def observe(self, session_id: str, calls: Sequence[ToolCall]) -> RepetitionVerdict:
        """Record one turn's calls and return whether the model is stuck.

        A turn with no calls still counts as a turn: it slides the window along,
        so a model alternating between one call and a paragraph of prose is not
        credited with having moved on.
        """
        history = self._history(session_id)
        for call in calls:
            history.append(signature(call))

        counts: dict[tuple[str, str], int] = {}
        for entry in history:
            counts[entry] = counts.get(entry, 0) + 1

        worst = max(counts.items(), key=lambda item: item[1], default=None)
        if worst is None or worst[1] < self.ceiling:
            return RepetitionVerdict(window=self.window)
        return RepetitionVerdict(
            repeating=True, capability=worst[0][0], count=worst[1], window=self.window
        )

    def forget(self, session_id: str) -> None:
        """Drop what is remembered about one session."""
        self._recent.pop(session_id, None)

    def _history(self, session_id: str) -> deque[tuple[str, str]]:
        existing = self._recent.get(session_id)
        if existing is None:
            existing = deque(maxlen=self.window)
            self._recent[session_id] = existing
        self._recent.move_to_end(session_id)
        while len(self._recent) > max(self.max_sessions, 1):
            self._recent.popitem(last=False)
        return existing


__all__ = ["RepetitionDetector", "RepetitionVerdict"]
