"""SC-008: every shipped template applies cleanly and produces a working system.

The smoke test is per template rather than over the collection, so a failure
names the one that broke. It applies the template to an empty node, validates
the result against the real schema, and asserts the thing the template exists to
configure — which is what stops a template passing because it parsed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from config.constants.config_service import GOLDEN_TEMPLATES
from platform.config_service.catalogue import (
    CapabilityDescription,
    IntegrationSchema,
    StaticCatalogue,
    StaticIntegrationDirectory,
)
from platform.config_service.errors import UnknownTemplate
from platform.config_service.schema import RootConfig
from platform.config_service.templates import ConfigTemplate, TemplateLibrary, preview
from platform.config_service.validation import ConfigValidator
from platform.guardrails.engine import GuardrailEngine

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def library() -> TemplateLibrary:
    return TemplateLibrary.golden()


# --- FR-019: the diff comes before the application ---------------------------


def test_applying_a_template_to_an_empty_node_is_all_additions() -> None:
    template = ConfigTemplate(name="t", settings={"agents": {"tool_budget": 4}})

    diff = preview(template, {})

    assert [change.path for change in diff.changes] == ["agents.tool_budget"]
    assert diff.additions() == diff.changes
    assert diff.overwrites() == ()


def test_a_template_overwriting_a_deliberate_choice_shows_what_it_replaces() -> None:
    template = ConfigTemplate(name="t", settings={"agents": {"tool_budget": 4}})

    diff = preview(template, {"agents": {"tool_budget": 12}})

    assert diff.overwrites()[0].before == 12
    assert diff.overwrites()[0].after == 4
    assert "12" in diff.render() and "4" in diff.render()


def test_a_template_that_changes_nothing_says_so() -> None:
    template = ConfigTemplate(name="t", settings={"agents": {"tool_budget": 4}})

    diff = preview(template, {"agents": {"tool_budget": 4}})

    assert diff.empty
    assert "nothing" in diff.render()


def test_the_diff_and_the_application_cannot_disagree() -> None:
    """They are the same merge, which is the point of returning both together."""
    template = ConfigTemplate(name="t", settings={"agents": {"tool_budget": 4}})
    existing: dict[str, Any] = {"agents": {"max_iterations": 9}, "models": {}}

    diff = preview(template, existing)

    assert diff.settings == {"agents": {"max_iterations": 9, "tool_budget": 4}, "models": {}}


def test_a_template_leaves_a_field_it_does_not_mention_alone() -> None:
    template = ConfigTemplate(name="t", settings={"agents": {"tool_budget": 4}})

    diff = preview(template, {"policies": {"masking": {"level": "strict"}}})

    assert diff.settings["policies"] == {"masking": {"level": "strict"}}


def test_an_unknown_template_is_named_alongside_what_is_installed(
    library: TemplateLibrary,
) -> None:
    with pytest.raises(UnknownTemplate, match="chaos-engineering"):
        library.get("chaos-engineering")


# --- FR-020: the seven ship, and are the seven --------------------------------


def test_the_shipped_templates_are_exactly_the_declared_seven(
    library: TemplateLibrary,
) -> None:
    assert library.names() == tuple(sorted(GOLDEN_TEMPLATES))


def test_every_shipped_template_describes_itself(library: TemplateLibrary) -> None:
    """The console renders these; a blank card is a template nobody picks."""
    for name in library.names():
        template = library.get(name)
        assert template.title, name
        assert template.summary, name
        assert template.use_case, name


# --- T044 / SC-008: one smoke test per template ------------------------------


@pytest.fixture(scope="module")
def validator() -> ConfigValidator:
    """Return a validator over a catalogue holding everything the templates name."""
    return ConfigValidator(
        catalogue=StaticCatalogue.of([CapabilityDescription(name="placeholder")]),
        integrations=StaticIntegrationDirectory.of([IntegrationSchema(name="placeholder")]),
        guardrails=GuardrailEngine(),
    )


def test_the_shipped_templates_are_parsed_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request that builds a configuration service asked for the library.

    Each ask read and parsed every shipped YAML file again — 28 ms on the
    gateway, on `/v1/config`, `/v1/proposals`, `/v1/incidents` and every
    other route that resolves a node — for files that cannot change while
    the process runs. Parsed once, then the same library handed back.
    """
    from platform.config_service.templates import engine

    engine.forget_shipped_templates()
    parsed = {"files": 0}
    real_load = engine.load

    def counted(path: Path) -> ConfigTemplate:
        parsed["files"] += 1
        return real_load(path)

    monkeypatch.setattr(engine, "load", counted)

    first = TemplateLibrary.golden()
    second = TemplateLibrary.golden()

    assert parsed["files"] == len(GOLDEN_TEMPLATES)
    assert second is first
    assert first.names() == tuple(sorted(GOLDEN_TEMPLATES))


@pytest.mark.parametrize("name", GOLDEN_TEMPLATES)
def test_a_shipped_template_applies_to_an_empty_node_and_validates(
    library: TemplateLibrary, validator: ConfigValidator, name: str
) -> None:
    diff = library.preview(name, {})

    assert not diff.empty, f"{name} configures nothing"
    outcome = validator.validate(diff.settings)
    assert outcome.ok, f"{name}: {[str(error) for error in outcome.errors]}"


@pytest.mark.parametrize("name", GOLDEN_TEMPLATES)
def test_a_shipped_template_produces_a_runnable_configuration(
    library: TemplateLibrary, name: str
) -> None:
    config = RootConfig.of(library.apply(name, {}))

    assert config.agents.prompt_for("investigator").strip(), name
    assert config.agents.max_iterations >= 1, name
    assert config.agents.tool_budget >= 1, name


@pytest.mark.parametrize("name", GOLDEN_TEMPLATES)
def test_a_shipped_template_is_idempotent(library: TemplateLibrary, name: str) -> None:
    """Applying twice changes nothing the second time, or the diff lied."""
    once = library.apply(name, {})

    assert library.preview(name, once).empty, name


def test_the_triage_template_reports_into_a_chat_channel(library: TemplateLibrary) -> None:
    config = RootConfig.of(library.apply("incident-triage-slack", {}))

    assert [channel.channel for channel in config.surfaces.channels_for("critical")] == [
        "#incidents"
    ]
    assert config.surfaces.active_destinations()[0].kind == "chat"


def test_the_ci_template_ships_the_code_historian(library: TemplateLibrary) -> None:
    config = RootConfig.of(library.apply("ci-failure-investigation", {}))

    historian = config.agents.subagent("code-historian")
    assert historian is not None
    assert historian.enabled


def test_the_dr_template_cannot_change_anything(library: TemplateLibrary) -> None:
    """A validation run that could change something changed it during the check."""
    config = RootConfig.of(library.apply("dr-validation", {}))

    assert not config.capabilities.allows("rollout-restart", ("kubernetes", "remediation"))
    assert config.policies.approvals.requires_approval("write_reversible")


def test_the_advisory_template_recommends_without_remembering(
    library: TemplateLibrary,
) -> None:
    config = RootConfig.of(library.apply("observability-advisory", {}))

    assert config.policies.memory.read_enabled
    assert not config.policies.memory.write_enabled


def test_the_alert_fatigue_template_runs_on_a_short_budget(
    library: TemplateLibrary,
) -> None:
    triage = RootConfig.of(library.apply("incident-triage-slack", {}))
    fatigue = RootConfig.of(library.apply("alert-fatigue-reduction", {}))

    assert fatigue.agents.tool_budget < triage.agents.tool_budget


def test_no_shipped_template_carries_a_secret_shaped_value(
    library: TemplateLibrary, validator: ConfigValidator
) -> None:
    for name in library.names():
        assert validator.secret_shaped(library.apply(name, {})) == (), name
