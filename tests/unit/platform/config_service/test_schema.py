"""The declared schema: defaults, typed reads, and the closed field set.

The first test is the load-bearing one. A node with no configuration must
resolve to a working system, because that is what makes configuration something
a team changes rather than something a deployment needs before it can start.
"""

from __future__ import annotations

import pytest

from config.constants.investigation import DEFAULT_TOOL_BUDGET, MAX_INVESTIGATION_LOOPS
from config.constants.llm import DEFAULT_MODEL_ID, DEFAULT_PROVIDER
from config.constants.security import DEFAULT_MASKING_POLICY, SIDE_EFFECT_WRITE_REVERSIBLE
from config.prompts.investigation import DEFAULT_RUNTIME_SYSTEM_PROMPT
from platform.config_service.errors import ConfigInvalid
from platform.config_service.schema import RootConfig
from platform.config_service.schema.policies import GUARDRAIL_MODE_ENFORCING

pytestmark = pytest.mark.unit


# --- T016: an empty node is a working deployment -----------------------------


def test_a_node_with_no_configuration_resolves_to_working_defaults() -> None:
    config = RootConfig.of({})

    assert config.agents.max_iterations == MAX_INVESTIGATION_LOOPS
    assert config.agents.tool_budget == DEFAULT_TOOL_BUDGET
    assert config.agents.prompt_for("investigator") == DEFAULT_RUNTIME_SYSTEM_PROMPT
    assert config.models.for_role("investigator").provider == DEFAULT_PROVIDER
    assert config.models.for_role("investigator").model == DEFAULT_MODEL_ID
    assert config.capabilities.allows("kubectl-get-pods")
    assert config.policies.memory.read_enabled
    assert config.policies.masking.level == DEFAULT_MASKING_POLICY
    assert config.policies.guardrails.mode == GUARDRAIL_MODE_ENFORCING
    assert config.policies.approvals.threshold == SIDE_EFFECT_WRITE_REVERSIBLE


def test_the_defaults_are_not_stored_anywhere() -> None:
    """FR-015: a default is a code constant, never a row somebody has to migrate."""
    assert RootConfig.read({}) == (RootConfig(), ())


# --- The closed field set ----------------------------------------------------


def test_an_undeclared_section_is_a_field_level_error() -> None:
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of({"agentz": {}})

    assert raised.value.paths() == ("agentz",)


def test_an_undeclared_field_inside_a_section_names_its_full_path() -> None:
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of({"policies": {"masking": {"levle": "off"}}})

    assert raised.value.paths() == ("policies.masking.levle",)


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of(
            {
                "agents": {"tool_budget": "eight"},
                "policies": {"masking": {"level": "maximum"}},
                "models": {"investigator": {"provider": "nowhere"}},
            }
        )

    assert set(raised.value.paths()) == {
        "agents.tool_budget",
        "policies.masking.level",
        "models.investigator.provider",
    }


# --- Typed reads -------------------------------------------------------------


def test_a_budget_may_be_lowered_but_not_raised_past_the_constant() -> None:
    """Article II: the ceiling is a named constant, not an operator's opinion."""
    assert RootConfig.of({"agents": {"max_iterations": 5}}).agents.max_iterations == 5

    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of({"agents": {"max_iterations": MAX_INVESTIGATION_LOOPS + 1}})

    assert raised.value.paths() == ("agents.max_iterations",)


def test_a_prompt_override_replaces_the_shipped_prompt() -> None:
    config = RootConfig.of({"agents": {"prompts": {"investigator": "Be brief."}}})

    assert config.agents.prompt_for("investigator") == "Be brief."
    assert config.agents.prompt_for("diagnose") == DEFAULT_RUNTIME_SYSTEM_PROMPT


def test_a_mis_spelled_switch_value_is_refused_rather_than_read_as_off() -> None:
    """An ablation that silently ran with memory off would publish a false table."""
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of({"policies": {"memory": {"read_enabled": "ture"}}})

    assert raised.value.paths() == ("policies.memory.read_enabled",)


def test_a_switch_written_the_yaml_way_is_accepted() -> None:
    config = RootConfig.of({"policies": {"memory": {"read_enabled": "off"}}})

    assert config.policies.memory.read_enabled is False


def test_an_unknown_provider_is_refused_at_write() -> None:
    with pytest.raises(ConfigInvalid):
        RootConfig.of({"models": {"investigator": {"provider": "acme-ai"}}})


def test_an_unknown_model_role_is_not_a_configuration_field() -> None:
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of({"models": {"summariser": {"provider": "openai"}}})

    assert raised.value.paths() == ("models.summariser",)


# --- Capabilities ------------------------------------------------------------


def test_an_absent_allow_list_means_everything_and_an_empty_one_means_nothing() -> None:
    assert RootConfig.of({"capabilities": {}}).capabilities.allows("anything")
    assert not RootConfig.of({"capabilities": {"enabled": []}}).capabilities.allows("anything")


def test_a_disabled_capability_is_unavailable_and_says_why() -> None:
    config = RootConfig.of({"capabilities": {"disabled": ["kubectl-delete"]}})

    assert not config.capabilities.allows("kubectl-delete")
    assert config.capabilities.refusal_for("kubectl-delete") == "disabled for this team"
    assert config.capabilities.refusal_for("kubectl-get-pods") is None


def test_a_disabled_tag_switches_off_a_whole_domain() -> None:
    config = RootConfig.of({"capabilities": {"disabled_tags": ["remediation"]}})

    assert not config.capabilities.allows("restart-deployment", ("kubernetes", "remediation"))
    assert config.capabilities.allows("get-pods", ("kubernetes",))


def test_deny_beats_allow() -> None:
    config = RootConfig.of({"capabilities": {"enabled": ["a"], "disabled": ["a"]}})

    assert not config.capabilities.allows("a")


# --- Integrations ------------------------------------------------------------


def test_an_integration_names_a_vault_entry_rather_than_carrying_a_secret() -> None:
    config = RootConfig.of(
        {
            "integrations": {
                "active": [{"name": "datadog", "credential": "datadog-prod", "site": "eu1"}]
            }
        }
    )

    entry = config.integrations.for_name("datadog")
    assert entry is not None
    assert entry.credential == "datadog-prod"
    assert entry.site == "eu1"
    assert not hasattr(entry, "api_key")


def test_an_integration_field_the_schema_does_not_declare_is_refused() -> None:
    """``api_key`` is not a typo an operator gets to make quietly."""
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of({"integrations": {"active": [{"name": "datadog", "api_key": "abc"}]}})

    assert raised.value.paths() == ("integrations.active[0].api_key",)


def test_the_same_integration_configured_twice_is_refused() -> None:
    with pytest.raises(ConfigInvalid):
        RootConfig.of({"integrations": {"active": [{"name": "datadog"}, {"name": "datadog"}]}})


# --- Approvals ---------------------------------------------------------------


def test_the_approval_threshold_cannot_be_raised_above_a_reversible_write() -> None:
    """Article III is not a field an operator can switch off."""
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of({"policies": {"approvals": {"threshold": "destructive"}}})

    assert raised.value.paths() == ("policies.approvals.threshold",)


def test_a_read_needs_no_approval_and_a_write_does() -> None:
    approvals = RootConfig.of({}).policies.approvals

    assert not approvals.requires_approval("read")
    assert not approvals.requires_approval("read_sensitive")
    assert approvals.requires_approval("write_reversible")
    assert approvals.requires_approval("destructive")


def test_an_autonomous_capability_skips_the_approval_it_would_otherwise_need() -> None:
    approvals = RootConfig.of(
        {"policies": {"approvals": {"autonomous_capabilities": ["rollout-restart"]}}}
    ).policies.approvals

    assert not approvals.requires_approval("write_reversible", "rollout-restart")
    assert approvals.requires_approval("write_reversible", "delete-namespace")


def test_an_undeclared_side_effect_level_is_treated_as_needing_approval() -> None:
    """Absence is never permission."""
    assert RootConfig.of({}).policies.approvals.requires_approval("whatever")


# --- Sub-agents --------------------------------------------------------------


def test_a_subagent_topology_is_configuration() -> None:
    config = RootConfig.of(
        {
            "agents": {
                "subagents": [
                    {
                        "name": "code-historian",
                        "description": "Reads recent changes",
                        "capabilities": ["git-log", "list-deployments"],
                        "max_iterations": 4,
                    }
                ]
            }
        }
    )

    historian = config.agents.subagent("code-historian")
    assert historian is not None
    assert historian.capabilities == ("git-log", "list-deployments")
    assert historian.max_iterations == 4
    assert config.agents.enabled_subagents() == (historian,)


def test_a_disabled_subagent_is_not_dispatched() -> None:
    config = RootConfig.of({"agents": {"subagents": [{"name": "historian", "enabled": False}]}})

    assert config.agents.enabled_subagents() == ()


def test_a_subagent_without_a_name_is_refused() -> None:
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of({"agents": {"subagents": [{"description": "nameless"}]}})

    assert raised.value.paths() == ("agents.subagents[0].name",)


def test_two_subagents_with_one_name_are_refused() -> None:
    with pytest.raises(ConfigInvalid):
        RootConfig.of({"agents": {"subagents": [{"name": "a"}, {"name": "a"}]}})


# --- Surfaces ----------------------------------------------------------------


def test_a_channel_accepts_only_what_meets_its_floor() -> None:
    config = RootConfig.of(
        {
            "surfaces": {
                "channels": [
                    {"platform": "slack", "channel": "#pages", "min_severity": "critical"},
                    {"platform": "slack", "channel": "#noise"},
                ]
            }
        }
    )

    assert [c.channel for c in config.surfaces.channels_for("critical")] == ["#pages", "#noise"]
    assert [c.channel for c in config.surfaces.channels_for("info")] == ["#noise"]


def test_an_unknown_chat_platform_is_refused() -> None:
    with pytest.raises(ConfigInvalid):
        RootConfig.of({"surfaces": {"channels": [{"platform": "irc", "channel": "#sre"}]}})


# --- What the runtime and the console read -----------------------------------


def test_every_capability_reference_is_collected_from_everywhere_one_can_appear() -> None:
    config = RootConfig.of(
        {
            "capabilities": {"disabled": ["a"], "parameters": {"b": {"limit": 1}}},
            "agents": {"subagents": [{"name": "s", "capabilities": ["c"]}]},
            "policies": {"approvals": {"autonomous_capabilities": ["d"]}},
        }
    )

    assert set(config.capability_references()) == {"a", "b", "c", "d"}


def test_the_trace_records_the_configuration_a_run_started_under() -> None:
    config = RootConfig.of(
        {
            "models": {"investigator": {"provider": "ollama", "model": "llama3"}},
            "policies": {"memory": {"read_enabled": False}},
        }
    )

    summary = config.trace_summary()
    assert summary["config_models"] == {"investigator": "ollama/llama3"}
    assert summary["memory_read_enabled"] is False


def test_the_console_can_ask_which_fields_a_section_declares() -> None:
    from platform.config_service.schema.root import ROOT_SECTIONS, section_fields

    fields = section_fields()
    assert set(fields) == set(ROOT_SECTIONS)
    assert "masking" in fields["policies"]
