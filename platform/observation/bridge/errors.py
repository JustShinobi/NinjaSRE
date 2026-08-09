"""What the bridge refuses, and the name it refuses under.

Every one of these describes a source this deployment does not own and cannot
restart. That is the difference between them and the rest of
``platform/observation``: an unevaluable detector is this deployment's fault and
an unreachable Prometheus is somebody else's, and the second still has to reach
an operator rather than being absorbed.

**Unreachable raises rather than returning nothing.** An empty answer from a
healthy metrics system and no answer from a dead one are opposite facts, and a
threshold detector reading the resulting silence concludes the estate is fine.
The whole feature is worth less than nothing if that can happen, so the failure
travels as an exception and the caller turns it into a finding.
"""

from __future__ import annotations

from platform.observation.errors import ObservationError


class BridgeError(ObservationError):
    """Anything the observability bridge refuses."""


class MetricsSourceUnreachable(BridgeError):
    """The metrics system did not answer.

    Carries the source and the reason apart from the rendered sentence, because
    the incident this becomes names the source in its title and the reason in its
    cause, and re-parsing a message to split them is how the two drift.
    """

    def __init__(self, source: str, *, reason: str) -> None:
        super().__init__(
            f"the metrics source {source!r} did not answer: {reason}. Detectors that read "
            f"it report that they could not be evaluated; none of them reports that "
            f"nothing is wrong."
        )
        self.source = source
        self.reason = reason


class LogSourceUnreachable(BridgeError):
    """The log system did not answer."""

    def __init__(self, source: str, *, reason: str) -> None:
        super().__init__(
            f"the log source {source!r} did not answer: {reason}. An investigation that "
            f"asked for a resource's logs is told this rather than being handed an "
            f"empty result that reads as a quiet guest."
        )
        self.source = source
        self.reason = reason


class DashboardsUnreachable(BridgeError):
    """The dashboard system refused or could not be reached.

    A degradation rather than a failure of the report: a report without a link is
    a report, and a link to a dashboard nobody can open is a dead end with the
    appearance of an answer.
    """

    def __init__(self, source: str, *, reason: str) -> None:
        super().__init__(
            f"the dashboard source {source!r} is not reachable: {reason}. The report "
            f"omits the link and records why, rather than linking somewhere that "
            f"answers with a login page."
        )
        self.source = source
        self.reason = reason


class BridgeBoundExceeded(BridgeError):
    """A configured bound past what the constants allow.

    Refused where it is declared. A log window longer than the ceiling or a
    lookback past the maximum is a query that can take the operator's own
    monitoring down, which is the one failure this feature must not cause.
    """

    def __init__(self, *, parameter: str, requested: int, limit: int, constant: str) -> None:
        super().__init__(
            f"{parameter} of {requested} exceeds {limit}, which is {constant}. The bound "
            f"protects a system this deployment does not own; it is raised in the "
            f"constant or not at all."
        )
        self.parameter = parameter
        self.requested = requested
        self.limit = limit
        self.constant = constant


__all__ = [
    "BridgeBoundExceeded",
    "BridgeError",
    "DashboardsUnreachable",
    "LogSourceUnreachable",
    "MetricsSourceUnreachable",
]
