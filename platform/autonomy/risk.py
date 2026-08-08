"""How dangerous one action is, on a closed scale the capability's author sets.

The classification is declared at registration and not judged at the call. The
capability's author knows whether restarting a guest is reversible; the decision
point does not, and a model proposing the action certainly does not. Declaring
it once, in code, means the judgement is reviewed the way code is reviewed,
rather than re-derived by whatever is holding the action when it matters.

Three questions define the scale, and a class is the *worst* answer among them:
can it be undone, how far does it reach, and can it lose data or availability.
That is why ``moderate`` and ``high`` are not simply "bigger" — a one-resource
action that needs a restore to undo outranks a many-resource action that does
not.

**Absence is the top of the scale.** ``risk_class_of`` answers ``critical`` for
an action that declares nothing, and there is no fourth value meaning
"unclassified". A capability whose author forgot the field is a capability
nobody assessed, and the survivable reading of that is the pessimistic one.

**A value nobody defined raises.** A typo is different from an omission: it is
an author's decision that never took effect, and quietly treating it as
``critical`` would look exactly like the field having been left out.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from config.constants.autonomy import (
    RISK_CLASS_CRITICAL,
    RISK_CLASS_HIGH,
    RISK_CLASS_LOW,
    RISK_CLASS_MODERATE,
    RISK_CLASS_TRIVIAL,
    RISK_CLASSES,
)


class RiskClass(StrEnum):
    """One action's danger, least to most, as the capability declares it."""

    TRIVIAL = RISK_CLASS_TRIVIAL
    LOW = RISK_CLASS_LOW
    MODERATE = RISK_CLASS_MODERATE
    HIGH = RISK_CLASS_HIGH
    CRITICAL = RISK_CLASS_CRITICAL

    @property
    def rank(self) -> int:
        """Return this class's position on the scale, lowest is safest."""
        return RISK_CLASSES.index(self.value)

    def at_or_below(self, bound: RiskClass) -> bool:
        """Return whether this class is inside ``bound``.

        Inclusive. ``act_on_low_risk`` with a bound of ``low`` means "low and
        anything safer", which is what an operator setting a ceiling means.
        """
        return self.rank <= bound.rank

    @property
    def reversible(self) -> bool:
        """Return whether the action undoes itself, without a restore."""
        return self.rank <= RiskClass.MODERATE.rank

    @property
    def reaches_one_resource(self) -> bool:
        """Return whether the blast radius stops at the resource named."""
        return self.rank <= RiskClass.LOW.rank

    @property
    def can_lose_data(self) -> bool:
        """Return whether the action can destroy something with no other copy."""
        return self is RiskClass.CRITICAL

    @property
    def can_lose_availability(self) -> bool:
        """Return whether the action can take something down."""
        return self.rank >= RiskClass.LOW.rank

    def describe(self) -> str:
        """Return the sentence an operator reads beside this class."""
        return _DESCRIPTIONS[self]


_DESCRIPTIONS: Final[dict[RiskClass, str]] = {
    RiskClass.TRIVIAL: (
        "Reversible, reaches one resource, and loses neither data nor availability."
    ),
    RiskClass.LOW: (
        "Reversible, reaches one resource, and costs a brief loss of availability at most."
    ),
    RiskClass.MODERATE: ("Undone only by a further action, or reaching several resources at once."),
    RiskClass.HIGH: ("Not reversible without a restore, or reaching many resources at once."),
    RiskClass.CRITICAL: (
        "Can destroy data that has no other copy, or take an estate's availability down."
    ),
}


def risk_class_of(declared: str | None) -> RiskClass:
    """Return the class ``declared`` names, ``critical`` when it names nothing.

    Raises:
        ValueError: ``declared`` is a value the scale does not contain.
    """
    if declared is None or not declared.strip():
        return RiskClass.CRITICAL
    try:
        return RiskClass(declared.strip().lower())
    except ValueError as unknown:
        raise ValueError(
            f"{declared!r} is not a risk class, so the declaration says nothing; expected "
            f"one of {', '.join(RISK_CLASSES)}"
        ) from unknown


__all__ = [
    "RiskClass",
    "risk_class_of",
]
