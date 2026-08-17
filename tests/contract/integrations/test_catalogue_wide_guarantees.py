"""The promises that are about the catalogue as a whole rather than one vendor.

Everything beside this file asserts something per integration, parameterised, so
a failure names the vendor. These are the ones a per-vendor row cannot express:
they are true of the set or they are not true at all.

``every write is gated and reversible``
    A capability above ``read_sensitive`` needs a human and a way back. Checked
    per tool elsewhere; checked here as a property of the whole catalogue,
    because the failure mode is one vendor's write slipping in without either.

``every skill validates, bodies included``
    Binding, budgets, and the shell anti-pattern lint, over the real catalogue
    rather than a fixture. A skill that told the model to run a command against
    production would pass every other check in this directory.

``the catalogue fits the standing context budget``
    Every skill's index entry is paid on every turn. Eighty-odd of them is where
    that stops being free, and the ceiling has to be measured against the real
    set rather than estimated from one.

``two vendors in a domain are scored, not ranked by accident``
    A team with Loki and Elasticsearch has two log stores. Selection has to give
    both a score the rationale can explain; silently preferring whichever
    happened to be discovered first is the failure this catches.

``an unconfigured integration is excluded with a reason``
    Not merely absent. "Not in the catalogue" and "not configured for this team"
    look identical from a console, and only one of them is something an operator
    can fix.
"""

from __future__ import annotations

import pytest

from capabilities.registry.catalogue import registry_from, resolve_for
from capabilities.registry.discovery import discover
from capabilities.registry.scoring import Incident
from capabilities.registry.selection import select
from capabilities.registry.validation import failures
from config.constants.capabilities import MAX_CATALOGUE_METADATA_TOKENS
from core.capability.metadata import CapabilityKind, SideEffectLevel
from core.capability.ports import ConfiguredIntegrations
from integrations._catalogue.discovery import vendor_packages
from integrations._catalogue.gaps import gaps
from tests.contract.integrations.conftest import CATALOGUE

pytestmark = pytest.mark.contract

DISCOVERED = discover()
REGISTRY = registry_from(DISCOVERED)

#: Every capability that reaches a vendor in the catalogue, by evidence source.
VENDOR_TOOLS = tuple(
    found
    for found in DISCOVERED.tools
    if found.metadata.evidence_source in {entry.name for entry in CATALOGUE}
)


def test_the_catalogue_is_the_size_the_wave_set_out_to_deliver() -> None:
    """A count, so a package quietly failing to import is visible as a number."""
    assert len(vendor_packages()) == len(CATALOGUE)
    assert len(CATALOGUE) == 15, f"{len(CATALOGUE)} integrations are installed, not 15"


def test_every_recorded_gap_is_absent_from_the_catalogue_rather_than_broken() -> None:
    """FR-003: an honest gap is fine, a silent one is not, and a stale one is worse."""
    installed = {entry.name for entry in CATALOGUE}

    assert not installed & {gap.integration for gap in gaps()}


# --- SC-004: every write declares its level and provides a rollback -----------


def test_every_write_capability_is_gated_and_carries_a_way_back() -> None:
    writes = [
        found
        for found in VENDOR_TOOLS
        if found.metadata.side_effect_level > SideEffectLevel.READ_SENSITIVE
    ]

    assert writes, "a catalogue with no write capability proves nothing about approval"
    for found in writes:
        metadata = found.metadata
        assert metadata.requires_approval, f"{found.name}: writes without asking"
        assert metadata.approval_reason.strip(), f"{found.name}: asks without saying why"
        assert metadata.rollback_planner is not None or metadata.rollback_plan.strip(), (
            f"{found.name}: has no way back, so the approval gate has nothing to record"
        )


def test_a_rollback_planner_produces_a_plan_from_the_arguments_it_will_be_given() -> None:
    """A planner that raises is a rollback nobody finds out about until the gate runs."""
    planned = 0
    for found in VENDOR_TOOLS:
        planner = found.metadata.rollback_planner
        if planner is None:
            continue
        plan = planner.plan(dict.fromkeys(found.input_schema.get("properties", {}), "example"))
        assert plan.summary.strip(), f"{found.name}: produced a plan with no summary"
        assert plan.steps, f"{found.name}: produced a plan with no steps"
        planned += 1

    assert planned, "no capability in the catalogue declares a rollback planner"


def test_no_read_capability_asks_for_approval() -> None:
    """An approval prompt on a read teaches operators to click through the next one."""
    for found in VENDOR_TOOLS:
        if found.metadata.side_effect_level <= SideEffectLevel.READ_SENSITIVE:
            assert not found.metadata.requires_approval, f"{found.name}: gates a read"


# --- SC-005: every skill validates, bodies included --------------------------


def test_the_whole_capability_catalogue_validates_including_every_skill_body() -> None:
    """Binding, budgets, and the shell anti-pattern lint, over the real set."""
    found = failures(DISCOVERED, check_bodies=True)

    assert not found, "\n".join(str(failure) for failure in found)


def test_the_standing_skill_index_still_fits_the_turn_budget() -> None:
    """The number this ceiling was sized for is the one the catalogue now has."""
    total = sum(skill.metadata_tokens for skill in DISCOVERED.skills)

    assert total <= MAX_CATALOGUE_METADATA_TOKENS, (
        f"the skill index costs {total} tokens across {len(DISCOVERED.skills)} skills, over "
        f"the {MAX_CATALOGUE_METADATA_TOKENS} ceiling"
    )


def test_every_integration_contributes_exactly_one_methodology_skill() -> None:
    """Two skills for one vendor is two index entries competing with each other."""
    for entry in CATALOGUE:
        owned = [
            skill
            for skill in DISCOVERED.skills
            if skill.metadata.requires.integrations == (entry.name,)
        ]

        assert len(owned) == 1, f"{entry.name}: {len(owned)} skills require it alone"


# --- Acceptance scenario 5: two vendors in one domain ------------------------


def test_two_log_stores_are_both_scored_rather_than_one_being_preferred_by_accident() -> None:
    catalogue = resolve_for(REGISTRY, ConfiguredIntegrations(integrations=("loki", "openobserve")))

    result = select(
        catalogue,
        Incident(
            alert_source="alertmanager", summary="checkout is returning errors", domain="logstore"
        ),
    )

    scored = {found.name: found for found in result.scores}
    for name in ("loki_log_statistics", "openobserve_log_statistics"):
        assert name in scored, f"{name} was not scored at all"
        assert scored[name].rationale, f"{name} scored with no rationale to explain it"


def test_a_domain_with_two_vendors_offers_both_methodologies() -> None:
    """Neither is hidden: an operator who configured both can be directed to either."""
    catalogue = resolve_for(REGISTRY, ConfiguredIntegrations(integrations=("loki", "openobserve")))

    names = {skill.name for skill in catalogue.skills}

    assert {"logstore-loki", "logstore-openobserve"} <= names


# --- Acceptance scenario 6: unconfigured is excluded with a reason -----------


def test_an_integration_nobody_configured_is_excluded_with_the_requirement_named() -> None:
    catalogue = resolve_for(REGISTRY, ConfiguredIntegrations(integrations=("kubernetes",)))

    excluded = {found.name: found for found in catalogue.excluded}

    assert "openobserve_log_statistics" in excluded
    entry = excluded["openobserve_log_statistics"]
    assert entry.kind is CapabilityKind.TOOL
    assert entry.unmet == ("openobserve",)
    assert "not configured" in entry.reason


def test_a_team_that_configured_nothing_gets_an_empty_catalogue_and_every_reason() -> None:
    catalogue = resolve_for(REGISTRY, ConfiguredIntegrations())

    assert not [found for found in catalogue.tools if found in VENDOR_TOOLS]
    assert len(catalogue.excluded) >= len(VENDOR_TOOLS)
