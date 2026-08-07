"""The eight switches, and the property that makes every ablation number trustworthy.

An ablation run is only a measurement if it differs from the baseline in exactly
one respect. Everything else here follows from that: the switches are values
rather than global state, ``without`` returns a new set rather than flipping one,
an unknown name raises instead of being ignored, and the configuration each arm
ran under is recorded so "identical in every other respect" is checkable rather
than asserted.

The last of those is SC-004. It is verified here by comparing traces, which is
what the success criterion asks for, and it is verified at the level where a leak
would actually happen — the configuration handed to the run, not the prose in a
report.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.constants.evaluation import ABLATION_MECHANISMS, BASELINE_ARM
from core.agent.runtime_port import SeedCall
from core.agent.seed_calls import SeedCatalogue, SeedPlan
from core.pipeline.ports import UNRANKED
from platform.masking.policy import MaskingLevel
from tests.harness.ablation.config import (
    AblationConfig,
    AblationConfigError,
    baseline_config,
    load_configs,
    one_at_a_time,
    write_configs,
)
from tests.harness.ablation.switches import (
    MECHANISMS,
    MechanismSwitches,
    UnknownMechanism,
    mechanism,
)

pytestmark = pytest.mark.unit


# -- the vocabulary (T021) -----------------------------------------------------


def test_every_mechanism_the_requirement_names_has_a_switch() -> None:
    """FR-012, enumerated. Eight, and the eight the constant declares."""
    assert tuple(found.name for found in MECHANISMS) == ABLATION_MECHANISMS


def test_every_switch_names_the_control_it_flips_and_who_owns_it() -> None:
    """A switch nobody can trace to a real control is a switch that measures nothing."""
    for found in MECHANISMS:
        assert found.summary, f"{found.name} has no summary"
        assert found.control, f"{found.name} does not name the control it flips"
        assert found.owner, f"{found.name} does not name the package that owns it"


def test_an_unknown_mechanism_raises_rather_than_being_ignored() -> None:
    """An ablation that silently skipped an axis would publish an unmeasured number."""
    with pytest.raises(UnknownMechanism) as raised:
        mechanism("telepathy")

    assert "telepathy" in str(raised.value)
    assert "memory_read" in str(raised.value)


# -- wiring (T022) -------------------------------------------------------------


def test_switching_off_episodic_read_leaves_writing_alone() -> None:
    """The ablation worth running is a populated corpus the agent may not consult."""
    switches = MechanismSwitches().without("memory_read")

    assert not switches.memory.read_enabled
    assert switches.memory.write_enabled


def test_each_switch_reaches_its_owning_features_control() -> None:
    """T022: the switch is the feature's own control, not a second one beside it."""
    off = MechanismSwitches().without(*ABLATION_MECHANISMS)

    assert not off.memory.read_enabled
    assert not off.strategies.enabled
    assert not off.knowledge.topology_enabled
    assert not off.knowledge.knowledge_enabled
    assert off.masking.level is MaskingLevel.OFF
    assert not off.subagents_enabled
    assert not off.seed_calls_enabled
    assert not off.capability_planning_enabled


def test_a_disabled_planner_resolves_to_the_unranked_port() -> None:
    """Off means the deployment's own neutral implementation, not a stub of one."""
    off = MechanismSwitches().without("capability_planning")

    assert off.ranker(object()) is UNRANKED
    assert MechanismSwitches().ranker(UNRANKED) is UNRANKED


def test_a_disabled_seed_catalogue_is_the_empty_one() -> None:
    """A source with no plan starts cold, which is what "seed calls off" has to mean."""
    populated = SeedCatalogue().with_plan(
        SeedPlan(alert_source="alertmanager", calls=(SeedCall(capability="list_pods"),))
    )
    off = MechanismSwitches().without("seed_calls")

    assert off.seed_catalogue(populated).for_source("alertmanager") == ()
    assert MechanismSwitches().seed_catalogue(populated).for_source("alertmanager")


def test_disabled_subagents_leave_the_loop_with_no_specialists() -> None:
    """Not a specialist that refuses: a deployment that has none."""
    off = MechanismSwitches().without("subagents")

    assert off.subagents(("researcher",)) == ()
    assert MechanismSwitches().subagents(("researcher",)) == ("researcher",)


def test_without_returns_a_new_value_and_leaves_the_original_alone() -> None:
    """The bug this prevents is an arm leaking its switch into the run after it."""
    original = MechanismSwitches()
    ablated = original.without("topology")

    assert original.knowledge.topology_enabled
    assert not ablated.knowledge.topology_enabled
    assert ablated is not original


def test_switching_off_something_nobody_defined_raises() -> None:
    """The same refusal each owning feature already makes, at the harness level."""
    with pytest.raises(UnknownMechanism):
        MechanismSwitches().without("vibes")


# -- SC-004: identical in every other respect ----------------------------------


def test_one_switch_changes_exactly_one_thing_in_the_trace() -> None:
    """SC-004, verified by comparing traces rather than by assertion.

    Every mechanism, one at a time, against the baseline configuration. If any
    of them moved a second key, an ablation arm would differ from the baseline in
    two respects and the contribution attributed to it would be the sum of both.
    """
    baseline = MechanismSwitches().trace_summary()

    for name in ABLATION_MECHANISMS:
        ablated = MechanismSwitches().without(name).trace_summary()
        moved = {key for key in baseline if baseline[key] != ablated.get(key)}
        assert moved == set(mechanism(name).trace_keys), (
            f"disabling {name} moved {sorted(moved)}, not only its own keys"
        )
        assert set(ablated) == set(baseline), "an arm's trace has to have the baseline's shape"


def test_the_trace_says_which_mechanisms_were_disabled() -> None:
    """A results table has to be able to name its own arm from the run's record."""
    switches = MechanismSwitches().without("topology", "masking")

    assert switches.disabled_mechanisms() == ("topology", "masking")
    assert not switches.enabled("topology")
    assert switches.enabled("memory_read")


# -- declarative configuration (T023, FR-016) ----------------------------------


def test_the_baseline_arm_disables_nothing() -> None:
    """The arm every other one is measured against."""
    assert baseline_config().name == BASELINE_ARM
    assert baseline_config().disabled == ()
    assert baseline_config().is_baseline


def test_one_at_a_time_produces_a_baseline_and_one_arm_per_mechanism() -> None:
    """The suite the plan's diagram draws: nine runs for eight mechanisms."""
    configs = one_at_a_time()

    assert configs[0].is_baseline
    assert len(configs) == len(ABLATION_MECHANISMS) + 1
    assert tuple(found.disabled[0] for found in configs[1:]) == ABLATION_MECHANISMS


def test_a_configuration_naming_an_unknown_mechanism_is_refused_when_it_is_written() -> None:
    """FR-016: reproducible means it fails at the file, not three hours into a run."""
    with pytest.raises(AblationConfigError) as raised:
        AblationConfig(name="nonsense", disabled=("astrology",))

    assert "astrology" in str(raised.value)


def test_an_arm_may_not_call_itself_the_baseline() -> None:
    """Two rows called "baseline" is a report nobody can read."""
    with pytest.raises(AblationConfigError):
        AblationConfig(name=BASELINE_ARM, disabled=("topology",))


def test_a_configuration_round_trips_through_a_file(tmp_path: Path) -> None:
    """Declarative and reproducible: the file is the experiment (FR-016)."""
    configs = (
        baseline_config(),
        AblationConfig(
            name="no-learning",
            disabled=("memory_read", "memory_strategy"),
            description="the pre-memory baseline",
        ),
    )
    path = write_configs(configs, tmp_path / "ablation.yml")

    assert load_configs(path) == configs


def test_a_configuration_file_naming_an_unknown_mechanism_names_the_file(
    tmp_path: Path,
) -> None:
    """The failure a contributor sees has to say which file and which name."""
    path = tmp_path / "ablation.yml"
    path.write_text(
        "configurations:\n  - name: broken\n    disabled: [astrology]\n", encoding="utf-8"
    )

    with pytest.raises(AblationConfigError) as raised:
        load_configs(path)

    assert "ablation.yml" in str(raised.value)
    assert "astrology" in str(raised.value)


def test_the_switches_a_configuration_implies_are_derived_from_it_alone() -> None:
    """Reproducible: the file is the whole of what an arm ran under."""
    config = AblationConfig(name="no-graph", disabled=("topology",))
    switches = config.switches()

    assert not switches.knowledge.topology_enabled
    assert switches.knowledge.knowledge_enabled
    assert switches.disabled_mechanisms() == ("topology",)
