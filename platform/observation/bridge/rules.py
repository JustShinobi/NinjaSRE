"""The alerting rules the operator already wrote, and what would double-alert on them.

A deployment that arrives at a homelab and starts alerting on conditions the
operator's own Prometheus has been alerting on for a year has not added
monitoring; it has added a second pager for the same events. That system gets
turned off, and everything else this deployment does goes with it.

So: the rules are read, the shipped detectors declare what they cover, and where
the two meet the operator is shown **both definitions** and told which one will
produce signals. The precedence rule of FR-006 decides which — this module does
not decide anything, it reports.

**Overlap is detected by metric, not by meaning.** A detector declares the
metrics its signal is derived from; a rule whose expression mentions one of them
is a candidate. That is deliberately a slightly loose test in one direction and a
tight one in the other: a false overlap costs an operator one line in a report
they can dismiss, and a missed one costs them a duplicate page at three in the
morning. Anything cleverer would need to understand PromQL, which would be the
second query language this package refuses to have.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from platform.observation.bridge.ports import AlertRule
from platform.observation.bridge.precedence import SignalPrecedence
from platform.observation.detectors.model import DetectorDeclaration


@dataclass(frozen=True, slots=True)
class CoverageClaim:
    """What one shipped detector says it is watching, in the metrics system's terms.

    Declared rather than derived. A detector reads a *signal*, and the signal's
    relationship to the metrics an exporter publishes is a fact about how the
    deployment was wired — which is exactly the sort of thing that has to be
    written down if a report is going to be able to say "these two are the same
    condition".
    """

    detector_id: str
    signal: str
    metrics: tuple[str, ...]

    def covers(self, rule: AlertRule) -> bool:
        """Return whether ``rule`` alerts on a metric this detector also watches."""
        return any(metric in rule.expression for metric in self.metrics)


@dataclass(frozen=True, slots=True)
class RuleOverlap:
    """One shipped detector and one existing rule that alert on the same thing.

    Both definitions travel together, because the operator's decision is which
    of the two they want and they cannot make it from a name.
    """

    detector_id: str
    detector_description: str
    detector_condition: str
    rule_name: str
    rule_expression: str
    rule_source_file: str
    rule_group: str
    signal: str
    winner: str
    reason: str

    @property
    def summary(self) -> str:
        """Return the paragraph an operator reads about this duplication."""
        where = f"{self.rule_source_file}:{self.rule_group}".rstrip(":")
        return (
            f"{self.rule_name!r} in {where} already alerts on this condition "
            f"({self.rule_expression}), and the shipped detector {self.detector_id!r} "
            f"covers it too ({self.detector_condition}). Precedence for {self.signal!r} "
            f"is {self.winner!r}: {self.reason}"
        )


def overlaps(
    detectors: Sequence[DetectorDeclaration],
    rules: Sequence[AlertRule],
    *,
    claims: Sequence[CoverageClaim],
    precedence: SignalPrecedence | None = None,
) -> tuple[RuleOverlap, ...]:
    """Return every place a shipped detector and an existing rule cover one condition.

    Reported, never resolved here. Silently disabling a detector because a rule
    looked similar would be this deployment deciding it understood somebody
    else's alerting, and doing so without saying anything.
    """
    resolved = precedence or SignalPrecedence()
    by_id = {detector.detector_id: detector for detector in detectors}

    found: list[RuleOverlap] = []
    for claim in claims:
        detector = by_id.get(claim.detector_id)
        if detector is None:
            continue
        for rule in rules:
            if not claim.covers(rule):
                continue
            found.append(
                RuleOverlap(
                    detector_id=detector.detector_id,
                    detector_description=detector.description,
                    detector_condition=_condition_of(detector),
                    rule_name=rule.name,
                    rule_expression=rule.expression,
                    rule_source_file=rule.source_file,
                    rule_group=rule.group,
                    signal=claim.signal,
                    winner=resolved.winner_for(claim.signal),
                    reason=resolved.reason_for(claim.signal),
                )
            )
    return tuple(found)


def _condition_of(detector: DetectorDeclaration) -> str:
    """Return the detector's own condition, in one line an operator can compare."""
    condition = detector.condition
    if condition.describes_a_number():
        return (
            f"{detector.signal} {condition.comparison.value} {condition.fire_value:g} "
            f"for {detector.for_seconds}s"
        )
    return f"{detector.signal} {condition.kind.value} for {detector.for_seconds}s"


__all__ = ["CoverageClaim", "RuleOverlap", "overlaps"]
