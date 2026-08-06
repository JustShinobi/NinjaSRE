"""T048 to T050: configuration reaching the things that read it.

Every one of these seams shipped with a ``for_team`` constructor and a docstring
saying this feature would fill it. The tests assert the filling, and one of them
asserts the property that made a single module worth it: all the bindings come
from one resolution, so they cannot disagree about which team they configure.
"""

from __future__ import annotations

import pytest

from platform.config_service.bindings import (
    RuntimeBindings,
    configured_integrations,
    subagent_source,
)
from platform.config_service.effective import EffectiveConfig
from platform.config_service.schema import RootConfig
from platform.masking.policy import MaskingLevel

pytestmark = pytest.mark.unit


def bindings(settings: dict[str, object], node_id: str = "team-payments") -> RuntimeBindings:
    """Return the bindings a node carrying ``settings`` produces."""
    config, errors = RootConfig.read(settings)
    assert errors == (), errors
    return RuntimeBindings.of(EffectiveConfig(node_id=node_id, values=settings, config=config))


# --- T049: the policy switches ------------------------------------------------


def test_a_node_with_no_configuration_binds_the_shipped_defaults() -> None:
    bound = bindings({})

    assert bound.memory.read_enabled and bound.memory.write_enabled
    assert bound.strategy.enabled
    assert bound.knowledge.topology_enabled and bound.knowledge.knowledge_enabled
    assert bound.trust.masking_enabled and bound.trust.guardrails_enabled


def test_the_memory_switches_reach_the_memory_policy() -> None:
    bound = bindings({"policies": {"memory": {"read_enabled": False}}})

    assert not bound.memory.read_enabled
    assert bound.memory.write_enabled


def test_the_strategy_switch_is_independent_of_the_memory_switches() -> None:
    """ "Do playbooks help, given the episodes were already there" is its own run."""
    bound = bindings({"policies": {"strategy": {"enabled": False}}})

    assert not bound.strategy.enabled
    assert bound.memory.read_enabled


def test_the_knowledge_switches_reach_the_knowledge_policy() -> None:
    bound = bindings(
        {"policies": {"knowledge": {"topology_enabled": False, "knowledge_base_enabled": True}}}
    )

    assert not bound.knowledge.topology_enabled
    assert bound.knowledge.knowledge_enabled


def test_the_masking_level_reaches_the_trust_controls() -> None:
    bound = bindings({"policies": {"masking": {"level": "strict"}}})

    assert bound.trust.policy.level is MaskingLevel.STRICT


def test_a_custom_masking_pattern_reaches_the_policy() -> None:
    bound = bindings(
        {
            "policies": {
                "masking": {"custom_patterns": [{"name": "ticket", "pattern": "TICKET-[0-9]{4}"}]}
            }
        }
    )

    assert [pattern.name for pattern in bound.trust.policy.custom_patterns] == ["ticket"]


def test_observing_guardrails_alters_nothing_but_does_not_remove_the_engine() -> None:
    """The engine cannot be removed from the boundary by any configuration."""
    bound = bindings({"policies": {"guardrails": {"mode": "observing"}}})

    assert not bound.trust.guardrails_enabled
    assert bound.trust.engine() is not None
    assert bound.trust.engine().audit_only


# --- T050: the sub-agent topology --------------------------------------------


def test_a_team_that_declares_no_subagents_gets_the_shipped_ones() -> None:
    declared = subagent_source(RootConfig().agents).definitions()

    assert len(declared) >= 5
    assert "log-analyst" in {each.name for each in declared}


def test_a_declared_subagent_replaces_the_shipped_set() -> None:
    bound = bindings(
        {
            "agents": {
                "subagents": [
                    {
                        "name": "code-historian",
                        "description": "Reads recent changes",
                        "capabilities": ["git-log"],
                        "max_iterations": 4,
                    }
                ]
            }
        }
    )

    declared = bound.subagents.definitions()
    assert [each.name for each in declared] == ["code-historian"]
    assert declared[0].max_iterations == 4
    assert declared[0].capabilities == ("git-log",)


def test_a_disabled_subagent_is_not_registered() -> None:
    bound = bindings(
        {
            "agents": {
                "subagents": [
                    {"name": "a", "description": "d", "capabilities": ["x"]},
                    {"name": "b", "description": "d", "capabilities": ["x"], "enabled": False},
                ]
            }
        }
    )

    assert [each.name for each in bound.subagents.definitions()] == ["a"]


def test_a_subagent_the_runtime_would_refuse_is_dropped_rather_than_raised_on() -> None:
    """A bad row must not stop the investigation the good rows would have run."""
    bound = bindings(
        {
            "agents": {
                "subagents": [
                    {"name": "usable", "description": "d", "capabilities": ["x"]},
                    {"name": "unusable", "description": "no capabilities and no domain"},
                ]
            }
        }
    )

    assert [each.name for each in bound.subagents.definitions()] == ["usable"]


# --- T048: what capability selection is told is available ---------------------


def test_the_configured_integrations_are_what_selection_sees() -> None:
    config = RootConfig.of(
        {
            "integrations": {
                "active": [
                    {"name": "datadog"},
                    {"name": "kubernetes", "enabled": False},
                ]
            }
        }
    )

    assert configured_integrations(config) == ("datadog",)


def test_the_bindings_expose_the_model_and_prompt_a_role_runs_on() -> None:
    bound = bindings(
        {
            "models": {"investigator": {"provider": "ollama", "model": "llama3"}},
            "agents": {"prompts": {"investigator": "Be brief."}},
        }
    )

    assert bound.model_for("investigator").model == "llama3"
    assert bound.prompt_for("investigator") == "Be brief."
    assert bound.prompt_for("diagnose").strip()


# --- The property that made one module worth it -------------------------------


def test_every_binding_names_the_same_node() -> None:
    bound = bindings({"policies": {"memory": {"read_enabled": False}}}, node_id="team-search")

    summary = bound.trace_summary()
    assert summary["config_node"] == "team-search"
    assert summary["memory_read_enabled"] is False


def test_the_trace_records_which_configuration_the_run_started_under() -> None:
    bound = bindings({"models": {"intake": {"provider": "openai", "model": "gpt-x"}}})

    assert bound.trace_summary()["config_models"] == {"intake": "openai/gpt-x"}
