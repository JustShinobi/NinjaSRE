"""The switch is a real ablation axis, separate from the episodic memory ones.

The switch has to be independent of the two memory switches, because the question
it answers is not "does memory help" but "do playbooks help, given the episodes
were already there". A switch folded into memory reading would make the baseline
a run with no memory at all, and the comparison would measure recall.

The rest of this file is the same shape as the episodic policy's tests, for the
same reasons: an unknown axis raises rather than being ignored, because an
ablation that silently skipped one would publish a table claiming it measured
something it never varied.
"""

from __future__ import annotations

import pytest

from config.constants.memory import (
    NINJASRE_MEMORY_READ_ENV,
    NINJASRE_MEMORY_STRATEGY_ENV,
    NINJASRE_MEMORY_WRITE_ENV,
)
from platform.memory.policy import MEMORY_SWITCHES, MemoryPolicy
from platform.memory.strategy.policy import STRATEGY_SWITCH, STRATEGY_SWITCHES, StrategyPolicy

pytestmark = pytest.mark.unit


def test_the_strategy_axis_is_not_one_of_the_memory_axes() -> None:
    """An axis the evaluation harness can vary on its own."""
    assert STRATEGY_SWITCH not in MEMORY_SWITCHES
    assert not set(STRATEGY_SWITCHES) & set(MEMORY_SWITCHES)
    assert NINJASRE_MEMORY_STRATEGY_ENV not in {
        NINJASRE_MEMORY_READ_ENV,
        NINJASRE_MEMORY_WRITE_ENV,
    }


def test_disabling_strategies_leaves_episodic_memory_alone() -> None:
    """The baseline is a populated corpus, read as usual, with only synthesis off."""
    memory = MemoryPolicy()
    strategies = StrategyPolicy.disabled()

    assert memory.read_enabled
    assert memory.write_enabled
    assert not strategies.enabled


def test_without_returns_a_new_policy() -> None:
    """An ablation run must not leave the switch flipped for the run after it."""
    policy = StrategyPolicy()
    ablated = policy.without(STRATEGY_SWITCH)

    assert policy.enabled
    assert not ablated.enabled


def test_an_unknown_axis_raises() -> None:
    with pytest.raises(ValueError, match="unknown strategy switch"):
        StrategyPolicy().without("memory_read")


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF", " False "])
def test_the_environment_switch_reads_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(NINJASRE_MEMORY_STRATEGY_ENV, value)
    assert not StrategyPolicy.from_environment().enabled


@pytest.mark.parametrize("value", ["1", "true", "yes", "", "typo"])
def test_anything_else_reads_on(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """A mis-spelled value must not silently disable a measured mechanism."""
    monkeypatch.setenv(NINJASRE_MEMORY_STRATEGY_ENV, value)
    assert StrategyPolicy.from_environment().enabled


def test_unset_reads_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(NINJASRE_MEMORY_STRATEGY_ENV, raising=False)
    assert StrategyPolicy.from_environment().enabled


def test_the_trace_separates_configuration_from_outcome() -> None:
    """ "Playbooks were off" and "no playbook existed yet" are different facts."""
    assert StrategyPolicy().trace_summary() == {"memory_strategy_enabled": True}
    assert StrategyPolicy.disabled().trace_summary() == {"memory_strategy_enabled": False}
