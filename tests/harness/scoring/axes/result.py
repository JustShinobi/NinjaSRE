"""What one axis reports, whether it passed or not.

Both sides of every comparison are kept, and they are kept even when the axis
passed. Somebody comparing this release to the last one needs the *passing*
run's observed value to see what moved; a record that only kept the losing side
would make every comparison a re-run, which is exactly the cost the whole
feature exists to remove.

``applicable`` is the field that keeps FR-007 honest. An answer key asserts what
its author was willing to defend, so most keys leave some axes unasserted — and
an unasserted axis has to be *reported as unasserted*, not folded into the pass
count as a free win. A suite whose adversarial number was mostly scenarios that
never planted a confounder would be flattering and meaningless.

``measurements`` carries the numbers a trend is drawn from: distance, extra
calls, tokens, seconds. Numbers rather than sentences, because the regression
gate subtracts them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AxisScore:
    """One axis, checked, with the working shown."""

    name: str
    passed: bool
    applicable: bool = True
    expected: tuple[str, ...] = ()
    observed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    measurements: Mapping[str, float] = field(default_factory=dict)
    detail: str = ""

    @property
    def gates(self) -> bool:
        """Return whether this axis has a say in whether the scenario passed."""
        return self.applicable

    @property
    def failed(self) -> bool:
        """Return whether this axis was asserted and did not hold."""
        return self.applicable and not self.passed

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this axis."""
        return {
            "name": self.name,
            "passed": self.passed,
            "applicable": self.applicable,
            "expected": list(self.expected),
            "observed": list(self.observed),
            "missing": list(self.missing),
            "unexpected": list(self.unexpected),
            "measurements": dict(sorted(self.measurements.items())),
            "detail": self.detail,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> AxisScore:
        """Return the axis a stored record describes."""
        return cls(
            name=str(record["name"]),
            passed=bool(record.get("passed", False)),
            applicable=bool(record.get("applicable", True)),
            expected=tuple(str(item) for item in record.get("expected") or ()),
            observed=tuple(str(item) for item in record.get("observed") or ()),
            missing=tuple(str(item) for item in record.get("missing") or ()),
            unexpected=tuple(str(item) for item in record.get("unexpected") or ()),
            measurements={
                str(key): float(value) for key, value in (record.get("measurements") or {}).items()
            },
            detail=str(record.get("detail", "")),
        )


def not_asserted(name: str, *, detail: str) -> AxisScore:
    """Return the result for an axis this answer key says nothing about.

    Passing and inapplicable, which is not a contradiction: it does not fail the
    scenario, and it does not count towards the axis's pass rate either.
    """
    return AxisScore(name=name, passed=True, applicable=False, detail=detail)


def contains_all(haystack: str, needles: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Return the needles present in ``haystack`` and the ones absent, case-folded.

    Case-insensitive substring, matching what the scenario harness already does
    to the same fields. A stricter comparison here and a looser one there would
    make a keyword score differently depending on which layer asked.
    """
    folded = haystack.lower()
    present = tuple(needle for needle in needles if needle.lower() in folded)
    absent = tuple(needle for needle in needles if needle.lower() not in folded)
    return present, absent


__all__ = ["AxisScore", "contains_all", "not_asserted"]
