"""How well an investigation went, as a formula rather than as a judgement.

Effectiveness is not a report card. It feeds ranking, ranking decides which past
incident an agent reads first, and that changes what the agent does — so this
had to be something that can be versioned, tested, and argued with, and a
sentence of prose in a docstring is none of those.

    effectiveness = w_resolved   * resolved
                  + w_rootcause  * has_root_cause
                  + w_evidence   * evidence_backing_ratio
                  + w_trajectory * trajectory_efficiency

Four terms, each in ``[0, 1]``, weights that sum to one, so the result is in
``[0, 1]`` by construction rather than by clamping. Two of them deserve a word:

**``evidence_backing_ratio``** is validated claims over total claims. A run that
made three claims and backed all three scores 1.0; one that made ten and backed
three scores 0.3. Not "how much evidence was gathered" — an investigation that
gathered forty observations and concluded from none of them is worse than one
that gathered four and used them, and a count would say the opposite.

**``trajectory_efficiency``** is a bounded inverse of iterations used, not a
cliff. A run at or under the reference scores 1.0; twice the reference scores
0.5. The difference between eleven iterations and twelve is not the difference
between a good investigation and a bad one, and a threshold would say it was.

The version travels with every score. Changing a weight without bumping it would
leave a corpus of numbers meaning two different things with no way to tell which.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.memory import (
    EFFECTIVENESS_FORMULA_VERSION,
    EFFECTIVENESS_TRAJECTORY_REFERENCE_ITERATIONS,
    EFFECTIVENESS_WEIGHT_EVIDENCE,
    EFFECTIVENESS_WEIGHT_RESOLVED,
    EFFECTIVENESS_WEIGHT_ROOT_CAUSE,
    EFFECTIVENESS_WEIGHT_TRAJECTORY,
)


@dataclass(frozen=True, slots=True)
class EffectivenessInputs:
    """Everything the formula reads, and nothing it does not.

    A record rather than four parameters, because the call site is a lifecycle
    hook assembling these from three different places and a positional mistake
    there would be a silently wrong score rather than an error.
    """

    resolved: bool = False
    has_root_cause: bool = False
    validated_claims: int = 0
    total_claims: int = 0
    iterations: int = 0

    def __post_init__(self) -> None:
        if self.validated_claims < 0 or self.total_claims < 0:
            raise ValueError("claim counts cannot be negative")
        if self.validated_claims > self.total_claims:
            raise ValueError(
                f"{self.validated_claims} validated claims out of {self.total_claims} total — "
                "a claim cannot be backed by evidence without having been made"
            )
        if self.iterations < 0:
            raise ValueError("iteration count cannot be negative")


def evidence_backing_ratio(validated: int, total: int) -> float:
    """Return the share of claims that cite evidence, in ``[0, 1]``.

    A run that made no claims at all scores 0.0 rather than 1.0. Vacuous
    perfection would put an investigation that concluded nothing above one that
    concluded something and backed most of it.
    """
    if total <= 0:
        return 0.0
    return min(validated / total, 1.0)


def trajectory_efficiency(
    iterations: int,
    *,
    reference: int = EFFECTIVENESS_TRAJECTORY_REFERENCE_ITERATIONS,
) -> float:
    """Return the bounded inverse of ``iterations``, in ``(0, 1]``.

    Zero iterations scores 1.0: a run that answered before it needed a loop did
    not take a long trajectory, and penalising it would be penalising the best
    possible outcome.
    """
    if reference < 1:
        raise ValueError(
            f"the trajectory reference must be at least one iteration, got {reference}"
        )
    return reference / max(iterations, reference)


def effectiveness(inputs: EffectivenessInputs) -> float:
    """Return the documented score for one investigation, in ``[0, 1]``."""
    return (
        EFFECTIVENESS_WEIGHT_RESOLVED * float(inputs.resolved)
        + EFFECTIVENESS_WEIGHT_ROOT_CAUSE * float(inputs.has_root_cause)
        + EFFECTIVENESS_WEIGHT_EVIDENCE
        * evidence_backing_ratio(inputs.validated_claims, inputs.total_claims)
        + EFFECTIVENESS_WEIGHT_TRAJECTORY * trajectory_efficiency(inputs.iterations)
    )


def formula_version() -> int:
    """Return the version stamped onto every score this module produces."""
    return EFFECTIVENESS_FORMULA_VERSION


__all__ = [
    "EffectivenessInputs",
    "effectiveness",
    "evidence_backing_ratio",
    "formula_version",
    "trajectory_efficiency",
]
