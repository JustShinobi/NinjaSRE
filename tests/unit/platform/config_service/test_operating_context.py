"""The additive prompt field: named sections, inherited one section at a time.

``PromptOverrides`` replaces the shipped prompt. This replaces nothing — it adds
facts about the estate to whatever prompt the role is running with, and the
whole reason it is a *mapping* of named sections rather than one block of text
is that a section is the unit of inheritance. The organisation states what is
true everywhere, a team adds what is true only of theirs, and neither has to
restate the other's.

The inheritance tests here go through the real merge rather than through the
schema alone, because "sections inherit like any other configuration value" is a
claim about the merge and not about Pydantic.
"""

from __future__ import annotations

import pytest

from config.constants.agents import (
    MAX_OPERATING_CONTEXT_SECTIONS,
    OPERATING_CONTEXT_ROLES,
    OPERATING_CONTEXT_TOKEN_BUDGET,
)
from config.constants.llm import CHARACTERS_PER_TOKEN_ESTIMATE
from config.prompts.investigation import DEFAULT_RUNTIME_SYSTEM_PROMPT
from config.prompts.operating_context import OPERATING_CONTEXT_HEADING
from core.capability.tokens import estimate_tokens
from platform.config_service.errors import ConfigInvalid
from platform.config_service.merge import Layer, merge_layers
from platform.config_service.schema import RootConfig
from platform.config_service.schema.agents import OperatingContext

pytestmark = pytest.mark.unit


LXC = "Containers are LXC guests; their metrics come from the host, by vmid."
MTU = "The vk8s zone runs MTU 1450 over a 1450 underlay."


def context(**sections: str) -> dict[str, object]:
    """Return the settings document declaring ``sections`` as operating context."""
    return {"agents": {"operating_context": {"sections": dict(sections)}}}


# --- The section list --------------------------------------------------------


def test_a_deployment_that_writes_nothing_has_no_operating_context() -> None:
    """The zero-configuration deployment pays nothing, in tokens or in text."""
    config = RootConfig.of({})

    assert config.agents.operating_context.sections == {}
    assert config.agents.operating_context.render() == ""
    assert config.agents.system_prompt_for("investigator") == DEFAULT_RUNTIME_SYSTEM_PROMPT


def test_a_written_section_is_rendered_under_its_own_name() -> None:
    config = RootConfig.of(context(signals=LXC))

    rendered = config.agents.operating_context.render()

    assert rendered.startswith(OPERATING_CONTEXT_HEADING)
    assert "### signals" in rendered
    assert LXC in rendered


def test_sections_render_in_the_order_the_document_declares_them() -> None:
    """Deterministic, and meaningful: what an ancestor said comes before an addition."""
    config = RootConfig.of(context(signals=LXC, network=MTU))

    rendered = config.agents.operating_context.render()

    assert rendered.index("### signals") < rendered.index("### network")


def test_a_section_with_an_empty_body_is_not_rendered() -> None:
    """The removal a child writes: the heading survives merging, the text goes."""
    config = RootConfig.of(context(signals=LXC, network="   "))

    rendered = config.agents.operating_context.render()

    assert "### network" not in rendered
    assert "### signals" in rendered


def test_a_context_switched_off_renders_nothing_and_keeps_its_text() -> None:
    """The ablation switch. Article VII wants the contribution isolable."""
    config = RootConfig.of(
        {"agents": {"operating_context": {"sections": {"signals": LXC}, "enabled": False}}}
    )

    assert config.agents.operating_context.render() == ""
    assert config.agents.operating_context.sections["signals"] == LXC


# --- Names -------------------------------------------------------------------


def test_a_section_name_carrying_a_dot_is_refused() -> None:
    """A name is a path segment in the provenance table as well as a heading."""
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of(context(**{"network.zones": MTU}))

    assert raised.value.paths() == ("agents.operating_context",)


def test_a_section_with_a_blank_name_is_refused() -> None:
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of(context(**{"  ": MTU}))

    assert raised.value.paths() == ("agents.operating_context",)


def test_a_section_name_longer_than_a_heading_is_refused() -> None:
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of(context(**{"n" * 200: MTU}))

    assert raised.value.paths() == ("agents.operating_context",)


def test_more_sections_than_the_bound_are_refused() -> None:
    """Article II: the ceiling is a constant, and a chain of nodes can reach it."""
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of(
            context(
                **{f"section-{index}": MTU for index in range(MAX_OPERATING_CONTEXT_SECTIONS + 1)}
            )
        )

    assert raised.value.paths() == ("agents.operating_context.sections",)


# --- The token budget --------------------------------------------------------


def over_budget_body() -> str:
    """Return a body past the token budget and inside the per-field character bound.

    The two bounds are different things and the test is about the first: a body
    long enough to trip ``MAX_CONFIG_STRING_CHARS`` would be refused for its
    length and prove nothing about the budget.
    """
    return "fact " * (OPERATING_CONTEXT_TOKEN_BUDGET // CHARACTERS_PER_TOKEN_ESTIMATE * 5)


def test_a_context_past_the_token_budget_is_refused_rather_than_truncated() -> None:
    """Acceptance 3, and the contrast this feature is deliberate about.

    ``core/agent/context_budget.py`` truncates *evidence* at run time because
    evidence arrives during a run. Configuration does not: it was written by a
    person who can still be told.
    """
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of(context(background=over_budget_body()))

    assert raised.value.paths() == ("agents.operating_context",)


def test_the_refusal_names_the_overage_in_tokens() -> None:
    with pytest.raises(ConfigInvalid) as raised:
        RootConfig.of(context(background=over_budget_body()))

    message = raised.value.errors[0].message
    assert str(OPERATING_CONTEXT_TOKEN_BUDGET) in message
    assert "over" in message


def test_a_context_inside_the_budget_is_accepted() -> None:
    config = RootConfig.of(context(signals=LXC))

    assert 0 < config.agents.operating_context.tokens() <= OPERATING_CONTEXT_TOKEN_BUDGET


def test_the_budget_is_counted_by_the_estimator_the_run_time_budget_uses() -> None:
    """One estimator, so the two can never disagree about what a token is."""
    written = OperatingContext(sections={"signals": LXC, "network": MTU})

    assert written.tokens() == estimate_tokens(written.document())


def test_a_context_switched_off_is_still_measured() -> None:
    """Otherwise the refusal arrives on the day somebody enables it."""
    with pytest.raises(ConfigInvalid):
        RootConfig.of(
            {
                "agents": {
                    "operating_context": {
                        "sections": {"background": over_budget_body()},
                        "enabled": False,
                    }
                }
            }
        )


# --- Inheritance, through the real merge -------------------------------------


SECTIONS = "agents.operating_context.sections"


def merged(*layers: tuple[str, dict[str, object]]) -> tuple[RootConfig, dict[str, str]]:
    """Return the configuration and provenance ``layers`` produce, root-first."""
    result = merge_layers([Layer(node_id, values) for node_id, values in layers])
    config, errors = RootConfig.read(result.values)
    assert errors == ()
    return config, dict(result.provenance)


def test_a_child_adds_a_section_without_restating_its_parents() -> None:
    config, _ = merged(
        ("acme", context(signals=LXC)),
        ("team-payments", context(network=MTU)),
    )

    assert dict(config.agents.operating_context.sections) == {"signals": LXC, "network": MTU}


def test_a_child_overrides_one_section_by_name_and_keeps_the_rest() -> None:
    local = "Our own zone is flat; the vk8s note does not apply to us."
    config, _ = merged(
        ("acme", context(signals=LXC, network=MTU)),
        ("team-payments", context(network=local)),
    )

    assert dict(config.agents.operating_context.sections) == {"signals": LXC, "network": local}


def test_a_child_removes_an_inherited_section_by_emptying_its_body() -> None:
    """The clear-to-inherit shape one level down: the section stops being sent."""
    config, _ = merged(
        ("acme", context(signals=LXC, network=MTU)),
        ("team-payments", context(network="")),
    )

    rendered = config.agents.operating_context.render()

    assert "### network" not in rendered
    assert LXC in rendered


def test_each_section_reports_the_node_that_supplied_it() -> None:
    """Acceptance 2: provenance per section, exactly like any other value."""
    _, provenance = merged(
        ("acme", context(signals=LXC)),
        ("team-payments", context(network=MTU)),
    )

    assert provenance[f"{SECTIONS}.signals"] == "acme"
    assert provenance[f"{SECTIONS}.network"] == "team-payments"


def test_an_overridden_section_reports_the_node_that_overrode_it() -> None:
    _, provenance = merged(
        ("acme", context(network=MTU)),
        ("team-payments", context(network="Ours is flat.")),
    )

    assert provenance[f"{SECTIONS}.network"] == "team-payments"


# --- Assembly onto the prompt ------------------------------------------------


def test_the_context_is_appended_to_the_shipped_prompt_rather_than_replacing_it() -> None:
    config = RootConfig.of(context(signals=LXC))

    assembled = config.agents.system_prompt_for("investigator")

    assert assembled.startswith(DEFAULT_RUNTIME_SYSTEM_PROMPT)
    assert LXC in assembled


def test_the_context_is_appended_after_an_override_rather_than_replacing_it() -> None:
    """Acceptance 1, at the schema: the two coexist, in that order."""
    document = context(signals=LXC)
    document["agents"] = {**document["agents"], "prompts": {"investigator": "Be brief."}}  # type: ignore[dict-item]

    assembled = RootConfig.of(document).agents.system_prompt_for("investigator")

    assert assembled.startswith("Be brief.")
    assert assembled.index("Be brief.") < assembled.index(LXC)


def test_a_role_outside_the_named_set_is_byte_identical_to_its_prompt() -> None:
    """T-005: classification does not reason about the estate and does not pay for it."""
    config = RootConfig.of(context(signals=LXC))

    for role in ("intake", "diagnose"):
        assert role not in OPERATING_CONTEXT_ROLES
        assert config.agents.system_prompt_for(role) == config.agents.prompt_for(role)


def test_the_rendered_text_carries_no_trailing_or_doubled_whitespace() -> None:
    """The preview claims to be the exact string the model receives."""
    rendered = OperatingContext(sections={"a": f"  {LXC}  ", "b": MTU}).render()

    assert rendered == rendered.strip()
    assert "\n\n\n" not in rendered
