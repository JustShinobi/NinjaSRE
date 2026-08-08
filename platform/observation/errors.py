"""What observation refuses, and the name it refuses under.

Every one of these is a case where the wrong answer is worse than an error, and
the shape they share is that the wrong answer *looks like a working deployment*.

A detector with an unparseable condition that was skipped looks like a quiet
estate. A source that failed and reported no samples looks like a healthy one. A
detector that could call something with a side effect looks like automation and
is an actuator with none of the controls in front of it. Each is refused where
it is declared, because the alternative is finding out at three in the morning
from the absence of an alert.
"""

from __future__ import annotations


class ObservationError(Exception):
    """Anything observation refuses."""


class DetectorInvalid(ObservationError):
    """A detector declaration that could never do what it says.

    Carries the field and the reason rather than a rendered sentence, because
    the config service reports field-level errors and a caller assembling a form
    response needs the two apart.
    """

    def __init__(self, detector_id: str, *, field: str, reason: str) -> None:
        super().__init__(
            f"detector {detector_id or '<unnamed>'} is invalid: {field} {reason}. "
            f"A detector is refused where it is declared, because one that was "
            f"skipped at evaluation looks exactly like an estate with nothing wrong."
        )
        self.detector_id = detector_id
        self.field = field
        self.reason = reason


class UnknownDetector(ObservationError):
    """An operation naming a detector nothing declared."""

    def __init__(self, detector_id: str) -> None:
        super().__init__(
            f"no detector is declared as {detector_id!r}. Detectors come from "
            f"configuration; a name that resolves to nothing is a typo, not an "
            f"empty result."
        )
        self.detector_id = detector_id


class DetectorMayNotAct(ObservationError):
    """A detector referencing a capability that is not read-only.

    Refused at registration against the capability catalogue's declared level
    rather than by convention. A detector that can act is an autonomous actuator
    with none of the autonomy policy's controls in front of it, and it would
    start work without anybody having decided that it may.
    """

    def __init__(self, detector_id: str, *, capability: str, side_effect_level: str) -> None:
        super().__init__(
            f"detector {detector_id!r} references capability {capability!r}, which is "
            f"declared at {side_effect_level!r}. Detection reads: a detector that could "
            f"act would be acting before anything decided that it may."
        )
        self.detector_id = detector_id
        self.capability = capability
        self.side_effect_level = side_effect_level


class ObservationBoundExceeded(ObservationError):
    """A declaration asked for more than its bound allows.

    Distinct from a tick that reached its budget and stopped, which is a normal
    outcome. This is a declaration that could never fit — a window longer than
    retention, a duration below the floor — and it is refused where it is made.
    """

    def __init__(self, *, parameter: str, requested: int, limit: int, constant: str) -> None:
        super().__init__(
            f"{parameter} of {requested} exceeds {limit}, which is {constant}. "
            f"Bounds are raised deliberately, in the constant, not per detector."
        )
        self.parameter = parameter
        self.requested = requested
        self.limit = limit
        self.constant = constant


__all__ = [
    "DetectorInvalid",
    "DetectorMayNotAct",
    "ObservationBoundExceeded",
    "ObservationError",
    "UnknownDetector",
]
