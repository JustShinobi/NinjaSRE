"""The three postures, and why there is no fourth.

Never act, only diagnose and propose. Act on low-risk reversible things and ask
for the rest. Act on anything with a rollback plan and report afterwards. All
three are right — for different operators, for different resources, on different
days — and a deployment picks between them per scope rather than once.

The temptation at this point is a rule language. It is resisted deliberately: an
expression engine for autonomy is a place to write a bug that executes something
at four in the morning. Three ordered levels plus a configurable risk bound cover
every posture an operator has asked for, and anything they cannot express is a
case for an approval rather than for more grammar.

**The order is load-bearing.** It is what "least permissive" means when one
action targets several resources whose rules disagree, and it is what makes
"raise autonomy for two hours" a comparison rather than a special case.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from config.constants.autonomy import (
    AUTONOMY_LEVEL_ACT_AND_REPORT,
    AUTONOMY_LEVEL_ACT_ON_LOW_RISK,
    AUTONOMY_LEVEL_PROPOSE_ONLY,
    AUTONOMY_LEVELS,
    DEFAULT_AUTONOMY_LEVEL,
)


class AutonomyLevel(StrEnum):
    """How much this deployment may do without asking, in one scope."""

    PROPOSE_ONLY = AUTONOMY_LEVEL_PROPOSE_ONLY
    ACT_ON_LOW_RISK = AUTONOMY_LEVEL_ACT_ON_LOW_RISK
    ACT_AND_REPORT = AUTONOMY_LEVEL_ACT_AND_REPORT

    @property
    def rank(self) -> int:
        """Return this level's position, lowest is most cautious."""
        return AUTONOMY_LEVELS.index(self.value)

    @property
    def acts(self) -> bool:
        """Return whether this level can execute anything at all."""
        return self is not AutonomyLevel.PROPOSE_ONLY

    def describe(self) -> str:
        """Return the sentence an operator reads beside this level."""
        return _DESCRIPTIONS[self]


_DESCRIPTIONS: dict[AutonomyLevel, str] = {
    AutonomyLevel.PROPOSE_ONLY: (
        "Diagnose and propose. Nothing runs without a person deciding it should."
    ),
    AutonomyLevel.ACT_ON_LOW_RISK: (
        "Run what falls inside the configured risk bound; everything above it is proposed "
        "for approval."
    ),
    AutonomyLevel.ACT_AND_REPORT: (
        "Run anything that has a rollback plan, and say afterwards what was done."
    ),
}

#: What the absence of every rule resolves to.
DEFAULT_LEVEL: AutonomyLevel = AutonomyLevel(DEFAULT_AUTONOMY_LEVEL)


def least_permissive(levels: Iterable[AutonomyLevel]) -> AutonomyLevel:
    """Return the most cautious of ``levels``, the default when there are none.

    The default rather than the most permissive for an empty input, because an
    action that resolved against nothing has not been permitted by anything.
    """
    ranked = sorted(levels, key=lambda level: level.rank)
    return ranked[0] if ranked else DEFAULT_LEVEL


def level_of(declared: str | None) -> AutonomyLevel:
    """Return the level ``declared`` names, the default when it names nothing.

    Raises:
        ValueError: ``declared`` is a value the closed set does not contain.
    """
    if declared is None or not declared.strip():
        return DEFAULT_LEVEL
    try:
        return AutonomyLevel(declared.strip().lower())
    except ValueError as unknown:
        raise ValueError(
            f"{declared!r} is not an autonomy level; expected one of {', '.join(AUTONOMY_LEVELS)}"
        ) from unknown


__all__ = [
    "DEFAULT_LEVEL",
    "AutonomyLevel",
    "least_permissive",
    "level_of",
]
