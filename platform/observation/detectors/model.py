"""What a detector is: four condition kinds, two durations, and a grouping key.

A detector is a *declaration*, not code. That is the whole design and it is also
the whole risk, so the shape below is deliberately unable to grow into a second
programming language.

**Four condition kinds and no expressions.** Threshold, absence, rate of change,
state transition. Anything more expressive is a capability with a name, a
side-effect level and a test, not a string in a configuration file. The
temptation to add "just an arithmetic expression" is the temptation to ship an
interpreter nobody can validate, version, or explain to an operator at three in
the morning.

**Hysteresis is two numbers, not a mode.** ``fire_value`` and ``clear_value`` are
separate fields with no default relationship, because a single threshold with a
percentage of slack is the design that produces an incident per crossing on any
signal that oscillates. Declaring both makes the gap visible and reviewable.

**The grouping key is on the detector.** Correlation groups by it, so an
operator asking "why is this one incident with fifty subjects" reads the answer
off the detector rather than out of the correlation engine. Three values, all
inspectable: one incident per detector, one per parent, one per resource.

**Every duration is bounded and every bound is a constant.** A duration below
the floor is a threshold crossing rather than a problem; a window above the
ceiling is a retention decision made by somebody who was not thinking about
retention. Both are refused where they are declared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from config.constants.observation import (
    MAX_DETECTOR_ID_CHARS,
    MAX_DETECTOR_WINDOW_SECONDS,
    MIN_DETECTOR_DURATION_SECONDS,
)
from platform.notifications.models import Severity
from platform.observation.errors import DetectorInvalid, ObservationBoundExceeded


class ConditionKind(StrEnum):
    """The four things a detector may look for. There is no fifth."""

    #: A number above or below a value.
    THRESHOLD = "threshold"
    #: A series that has stopped arriving. The one most systems cannot express,
    #: because they only evaluate the samples they have.
    ABSENCE = "absence"
    #: A number changing faster than a value, per minute.
    RATE_OF_CHANGE = "rate_of_change"
    #: A state signal that entered — or left — a named state.
    STATE_TRANSITION = "state_transition"


class Comparison(StrEnum):
    """Which side of the threshold fires."""

    ABOVE = "above"
    BELOW = "below"


class GroupingKey(StrEnum):
    """How many incidents one firing across many resources becomes.

    ``DETECTOR`` is the default and the one that makes a node taking twenty
    guests with it a single incident with twenty subjects. ``RESOURCE`` is for
    the detector whose subjects genuinely have nothing to do with each other,
    and choosing it is a decision somebody makes rather than a default they
    inherit.
    """

    #: One incident for the whole detector, however many subjects it names.
    DETECTOR = "detector"
    #: One incident per parent resource — per node, per cluster, per namespace.
    PARENT = "parent"
    #: One incident per resource.
    RESOURCE = "resource"


@dataclass(frozen=True, slots=True)
class Condition:
    """What a detector looks for, in the terms of one of the four kinds.

    Fields that belong to another kind are ignored rather than refused, because
    a declaration that carried a threshold *and* an absence tolerance is a
    declaration somebody edited from one kind into another — and the validation
    that matters is that the fields this kind needs are present and sane.
    """

    kind: ConditionKind
    comparison: Comparison = Comparison.ABOVE
    #: The value that fires, for a threshold or a rate of change.
    fire_value: float = 0.0
    #: The value that clears. Distinct from ``fire_value`` on purpose: one
    #: number is how a signal that oscillates produces an incident per crossing.
    clear_value: float = 0.0
    #: How long a series may be quiet before an absence condition fires. Zero
    #: means "use the interval the source promised", which is the right default
    #: because the source is the only thing that knows.
    silent_after_seconds: int = 0
    #: For a state transition: the state that fires. Required for that kind.
    to_state: str = ""
    #: For a state transition: the state it must have come from. Empty means any,
    #: which is the common case — "it went unhealthy" rarely cares what from.
    from_state: str = ""

    def describes_a_number(self) -> bool:
        """Return whether this condition reads numeric samples."""
        return self.kind in {ConditionKind.THRESHOLD, ConditionKind.RATE_OF_CHANGE}


@dataclass(frozen=True, slots=True)
class DetectorDeclaration:
    """One thing the deployment watches for, and everything it needs to do so.

    Validated on construction rather than at evaluation. A detector that was
    skipped because its declaration was wrong looks exactly like an estate with
    nothing wrong, which is the failure mode the whole feature exists to remove.
    """

    detector_id: str
    name: str
    #: What is being watched for and why it matters, in the operator's terms.
    #: On the detector rather than in documentation, because the rationale for a
    #: threshold is what somebody needs at the moment they are deciding whether
    #: the threshold is wrong.
    description: str
    #: The resource kinds this applies to. Empty means every kind, which is
    #: right for a detector over ``estate.health`` and wrong for most others.
    resource_kinds: tuple[str, ...]
    signal: str
    condition: Condition
    for_seconds: int
    recovery_seconds: int
    severity: Severity = Severity.HIGH
    grouping_key: GroupingKey = GroupingKey.DETECTOR
    enabled: bool = True
    #: The team whose dispatch budget an incident from this detector spends, and
    #: whose escalation policy it follows. Empty means the deployment's own.
    team_node_id: str = ""
    #: Capabilities an investigation started from this detector should reach for
    #: first. Every one is checked against the catalogue's side-effect level at
    #: registration: a detector that could act is an actuator.
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self._check_identity()
        self._check_durations()
        self._check_condition()

    @property
    def longest_window_seconds(self) -> int:
        """Return the longest window this detector reads."""
        return max(self.for_seconds, self.recovery_seconds)

    def applies_to(self, kind: str) -> bool:
        """Return whether this detector watches resources of ``kind``."""
        return not self.resource_kinds or kind in self.resource_kinds

    def _check_identity(self) -> None:
        if not self.detector_id:
            raise DetectorInvalid("", field="detector_id", reason="is missing")
        if len(self.detector_id) > MAX_DETECTOR_ID_CHARS:
            raise ObservationBoundExceeded(
                parameter=f"detector id {self.detector_id!r}",
                requested=len(self.detector_id),
                limit=MAX_DETECTOR_ID_CHARS,
                constant="MAX_DETECTOR_ID_CHARS",
            )
        if not self.name:
            raise DetectorInvalid(self.detector_id, field="name", reason="is missing")
        if not self.description:
            raise DetectorInvalid(
                self.detector_id,
                field="description",
                reason=(
                    "is missing; an operator deciding whether a threshold is wrong needs "
                    "the reason beside it"
                ),
            )
        if not self.signal:
            raise DetectorInvalid(self.detector_id, field="signal", reason="names nothing to read")

    def _check_durations(self) -> None:
        for label, seconds in (
            ("for_seconds", self.for_seconds),
            ("recovery_seconds", self.recovery_seconds),
        ):
            if seconds < MIN_DETECTOR_DURATION_SECONDS:
                raise ObservationBoundExceeded(
                    parameter=f"{self.detector_id} {label}",
                    requested=seconds,
                    limit=MIN_DETECTOR_DURATION_SECONDS,
                    constant="MIN_DETECTOR_DURATION_SECONDS",
                )
            if seconds > MAX_DETECTOR_WINDOW_SECONDS:
                raise ObservationBoundExceeded(
                    parameter=f"{self.detector_id} {label}",
                    requested=seconds,
                    limit=MAX_DETECTOR_WINDOW_SECONDS,
                    constant="MAX_DETECTOR_WINDOW_SECONDS",
                )

    def _check_condition(self) -> None:
        condition = self.condition
        if condition.kind is ConditionKind.STATE_TRANSITION and not condition.to_state:
            raise DetectorInvalid(
                self.detector_id,
                field="condition.to_state",
                reason="is missing; a state transition has to name the state that fires",
            )
        if condition.kind is ConditionKind.ABSENCE and condition.silent_after_seconds < 0:
            raise DetectorInvalid(
                self.detector_id,
                field="condition.silent_after_seconds",
                reason="is negative",
            )
        if not condition.describes_a_number():
            return
        if (
            condition.comparison is Comparison.ABOVE
            and condition.clear_value > condition.fire_value
        ):
            raise DetectorInvalid(
                self.detector_id,
                field="condition.clear_value",
                reason=(
                    "sits above the firing value on an 'above' condition, so the incident "
                    "would clear before it opened"
                ),
            )
        if (
            condition.comparison is Comparison.BELOW
            and condition.clear_value < condition.fire_value
        ):
            raise DetectorInvalid(
                self.detector_id,
                field="condition.clear_value",
                reason=(
                    "sits below the firing value on a 'below' condition, so the incident "
                    "would clear before it opened"
                ),
            )


__all__ = [
    "Comparison",
    "Condition",
    "ConditionKind",
    "DetectorDeclaration",
    "GroupingKey",
]
