"""The closed risk scale, and what an action that declares nothing counts as."""

from __future__ import annotations

import pytest

from config.constants.autonomy import RISK_CLASSES, UNCLASSIFIED_RISK_CLASS
from platform.autonomy.risk import RiskClass, risk_class_of


def test_the_scale_is_the_declared_one_in_the_declared_order() -> None:
    assert tuple(member.value for member in RiskClass) == RISK_CLASSES
    assert [member.rank for member in RiskClass] == sorted(member.rank for member in RiskClass)


def test_an_action_with_no_declared_class_is_the_highest_class() -> None:
    """Absence is never permission, and never a fourth state either."""
    for missing in ("", "   ", None):
        assert risk_class_of(missing) is RiskClass.CRITICAL
    assert RiskClass.CRITICAL.value == UNCLASSIFIED_RISK_CLASS


def test_a_class_nobody_defined_is_refused_rather_than_defaulted() -> None:
    """A typo is an author's decision that never took effect, not a free pass."""
    with pytest.raises(ValueError, match="reckless"):
        risk_class_of("reckless")


def test_a_bound_admits_itself_and_everything_below_it() -> None:
    assert RiskClass.LOW.at_or_below(RiskClass.LOW)
    assert RiskClass.TRIVIAL.at_or_below(RiskClass.LOW)
    assert not RiskClass.MODERATE.at_or_below(RiskClass.LOW)
    assert RiskClass.CRITICAL.at_or_below(RiskClass.CRITICAL)


def test_every_class_says_what_it_means_by_reversibility_reach_and_loss() -> None:
    """The three questions the scale is defined by, answered per class."""
    for member in RiskClass:
        assert member.reversible in (True, False)
        assert member.reaches_one_resource in (True, False)
        assert member.can_lose_data in (True, False)
        assert member.can_lose_availability in (True, False)
        assert member.describe()

    assert RiskClass.TRIVIAL.reversible
    assert not RiskClass.TRIVIAL.can_lose_availability
    assert not RiskClass.CRITICAL.reversible
    assert RiskClass.CRITICAL.can_lose_data
