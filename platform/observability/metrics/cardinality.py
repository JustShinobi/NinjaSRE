"""What may be a label, and how many values it may take.

Two controls, and they answer different questions.

``LabelSet`` answers *which dimensions exist*. It is declared beside the
instrument and it refuses anything else by name. That is the control that stops
a pod name becoming a label, because the person adding it has to change the
declaration and explain themselves rather than pass an extra keyword.

``CardinalityGuard`` answers *how many values a permitted dimension may take*.
Even a legitimate label can be unbounded in a deployment nobody anticipated —
a team hierarchy generated per pull request, a model identifier that carries a
build number. Values beyond the budget collapse into one overflow bucket rather
than being dropped, so the total still adds up and the collapse is visible in
the numbers instead of being a silent gap.

Truncation happens before the budget is charged. A thousand values sharing a
long prefix are one series, not a thousand, and charging before truncating would
let a prefix spend the whole budget on what is really one dimension.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from config.constants.observability import (
    MAX_METRIC_LABEL_VALUE_CHARS,
    MAX_METRIC_LABEL_VALUES,
    METRIC_LABEL_OVERFLOW,
)

#: One bound label pairing, sorted by name so a series has exactly one key.
BoundLabels = tuple[tuple[str, str], ...]


class UnknownLabel(ValueError):
    """A metric was written with a label its instrument does not declare."""


@dataclass(frozen=True, slots=True)
class LabelSet:
    """The dimensions one instrument may carry, and nothing else."""

    names: tuple[str, ...] = ()

    def bind(self, labels: Mapping[str, str]) -> BoundLabels:
        """Return ``labels`` as a sorted series key.

        Sorted rather than in call order, because two orderings of the same
        labels are one time series and a dictionary's order is whatever the
        call site happened to type.

        Raises:
            UnknownLabel: a label this instrument does not declare. Refused
                rather than dropped: a caller who thought they were recording a
                dimension should find out, not discover it in a dashboard.
        """
        declared = set(self.names)
        undeclared = sorted(set(labels) - declared)
        if undeclared:
            allowed = ", ".join(self.names) or "none"
            raise UnknownLabel(
                f"{', '.join(undeclared)} is not a label this instrument declares "
                f"(it declares: {allowed}). A field with an unbounded value space is "
                f"not a label — put it on a span instead."
            )
        return tuple(sorted((name, value) for name, value in labels.items()))


@dataclass(slots=True)
class CardinalityGuard:
    """Bounds how many distinct values each instrument's labels may take."""

    ceiling: int = MAX_METRIC_LABEL_VALUES
    max_value_chars: int = MAX_METRIC_LABEL_VALUE_CHARS
    _seen: dict[tuple[str, str], set[str]] = field(default_factory=dict, repr=False)
    overflowed: dict[tuple[str, str], int] = field(default_factory=dict)

    def bound(self, instrument: str, label: str, value: str) -> str:
        """Return the value this label may actually carry.

        The original when it is within budget or already known, the overflow
        bucket otherwise. Never raises: a metric write is not a place to fail an
        investigation, and the collapse is recorded where an operator can see it.
        """
        shortened = value[: self.max_value_chars]
        key = (instrument, label)
        seen = self._seen.setdefault(key, set())

        if shortened in seen:
            return shortened
        if len(seen) < self.ceiling:
            seen.add(shortened)
            return shortened

        self.overflowed[key] = self.overflowed.get(key, 0) + 1
        return METRIC_LABEL_OVERFLOW

    def distinct(self, instrument: str, label: str) -> int:
        """Return how many values this label has admitted so far."""
        return len(self._seen.get((instrument, label), ()))

    def to_record(self) -> dict[str, Any]:
        """Return what a diagnostic bundle shows about bounded labels."""
        return {
            "ceiling": self.ceiling,
            "overflowed": [
                {"instrument": instrument, "label": label, "collapsed": count}
                for (instrument, label), count in sorted(self.overflowed.items())
            ],
        }


__all__ = ["BoundLabels", "CardinalityGuard", "LabelSet", "UnknownLabel"]
