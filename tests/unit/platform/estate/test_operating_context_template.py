"""The starting document, and the line between what was discovered and what was not.

Two properties matter more than the wording. The derived half has to be
*derived* — every line in it traceable to something the estate reports — and the
undiscovered half has to say it is undiscovered rather than arriving as an empty
heading, because an empty heading reads as a question nobody bothered to answer
rather than as one nobody can.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from config.constants.signals import SIGNAL_QUESTION_PRESSURE, SIGNAL_QUESTION_UP
from config.prompts.operating_context import (
    LXC_METRICS_FACT,
    TEMPLATE_DERIVED_LEAD,
    TEMPLATE_NOTHING_DISCOVERED,
    TEMPLATE_PROMPT_PEOPLE,
    TEMPLATE_SECTION_CRITICALITY,
    TEMPLATE_SECTION_NETWORK,
    TEMPLATE_SECTION_PEOPLE,
    TEMPLATE_SECTION_SIGNALS,
    TEMPLATE_SECTION_WHAT_RUNS,
)
from platform.config_service.schema.agents import OperatingContext
from platform.estate import operating_context as template_module
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE
from platform.estate.operating_context import (
    DiscoveredEstate,
    sections_of,
    summarise,
    template_for,
)
from platform.persistence.ports.estate_repository import Resource

pytestmark = pytest.mark.unit

SEEN = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

#: What the reference deployment holds: three nodes on one network and a row of
#: containers on another, each guest carrying the number its host's series are
#: keyed by.
CONFIGURED = ("proxmox", "prometheus")


def container(vmid: int, address: str, **attributes: object) -> Resource:
    """Return one guest as the estate holds it after an enrichment."""
    return Resource(
        resource_id=f"prox-ct-{vmid}",
        kind=KIND_CONTAINER,
        source="proxmox",
        native_id=f"lxc/HAL9000/2025-01-01/{vmid}",
        display_name=f"guest-{vmid}",
        attributes={"vmid": vmid, "address": address, "zone": "vk8s", **attributes},
        last_seen_at=SEEN,
    )


def node(name: str, address: str) -> Resource:
    """Return one hypervisor node as the estate holds it."""
    return Resource(
        resource_id=f"prox-node-{name}",
        kind=KIND_NODE,
        source="proxmox",
        native_id=f"node/HAL9000/{name}",
        display_name=name,
        attributes={"address": address, "zone": "mgmt"},
        last_seen_at=SEEN,
    )


def swept() -> DiscoveredEstate:
    """Return what a sweep of the reference deployment produces."""
    return summarise(
        [
            node("pve01", "10.20.10.11"),
            node("pve02", "10.20.10.12"),
            container(100, "10.20.30.4", criticality="critical"),
            container(101, "10.20.30.5", criticality="best-effort"),
            container(102, "10.20.30.6"),
        ],
        configured_integrations=CONFIGURED,
    )


def body(sections: tuple[tuple[str, str], ...], name: str) -> str:
    """Return the body of the named section."""
    return dict(sections)[name]


# --- what a swept estate produces --------------------------------------------


def test_the_template_carries_the_kinds_the_estate_actually_holds() -> None:
    written = body(template_for(swept()), TEMPLATE_SECTION_WHAT_RUNS)

    assert TEMPLATE_DERIVED_LEAD in written
    assert f"3 × {KIND_CONTAINER}" in written
    assert f"2 × {KIND_NODE}" in written


def test_the_template_carries_each_zone_and_the_network_its_addresses_sit_on() -> None:
    """Acceptance 5: the zones the estate discovered, with their /24s."""
    written = body(template_for(swept()), TEMPLATE_SECTION_NETWORK)

    assert "vk8s — 10.20.30.0/24" in written
    assert "mgmt — 10.20.10.0/24" in written


def test_a_zone_whose_addresses_disagree_offers_no_network_rather_than_one_of_them() -> None:
    split = summarise(
        [container(100, "10.20.30.4"), container(101, "10.90.90.5")],
        configured_integrations=CONFIGURED,
    )

    assert body(template_for(split), TEMPLATE_SECTION_NETWORK).count("network not established") == 1


def test_the_template_carries_the_source_that_answers_each_signal_question() -> None:
    """Acceptance 5's other half: the signal map's own answers, not a guess."""
    written = body(template_for(swept()), TEMPLATE_SECTION_SIGNALS)

    assert f"{SIGNAL_QUESTION_PRESSURE} — prometheus" in written
    assert f"{SIGNAL_QUESTION_UP} — proxmox" in written


def test_the_container_metrics_fact_is_in_the_template_whatever_the_estate_says() -> None:
    """The one fact that is about how containers report rather than about here."""
    assert LXC_METRICS_FACT in body(template_for(swept()), TEMPLATE_SECTION_SIGNALS)
    assert LXC_METRICS_FACT in body(template_for(DiscoveredEstate()), TEMPLATE_SECTION_SIGNALS)


def test_the_template_names_the_criticality_vocabulary_the_inventory_uses() -> None:
    """Criticality does not come from the hypervisor; it comes from the inventory."""
    written = body(template_for(swept()), TEMPLATE_SECTION_CRITICALITY)

    assert "best-effort" in written
    assert "critical" in written


def test_the_people_section_is_a_question_and_nothing_else() -> None:
    """Nothing derives who is called, and a template that guessed would be worse."""
    assert body(template_for(swept()), TEMPLATE_SECTION_PEOPLE) == TEMPLATE_PROMPT_PEOPLE


# --- what a deployment with no estate produces --------------------------------


def test_with_no_estate_the_template_is_the_same_five_questions() -> None:
    """A template whose shape depended on the sweep would ask two deployments
    different questions, and the questions are the half worth shipping."""
    names = [name for name, _ in template_for(DiscoveredEstate())]

    assert names == [name for name, _ in template_for(swept())]


def test_an_undiscovered_section_says_why_it_is_empty_before_it_asks() -> None:
    empty = template_for(DiscoveredEstate())

    assert TEMPLATE_NOTHING_DISCOVERED in body(empty, TEMPLATE_SECTION_WHAT_RUNS)
    assert TEMPLATE_NOTHING_DISCOVERED in body(empty, TEMPLATE_SECTION_NETWORK)


def test_the_derived_lead_appears_nowhere_a_deployment_discovered_nothing() -> None:
    """ "Discovered from this deployment's own estate" over an empty list is a lie."""
    empty = template_for(DiscoveredEstate())

    assert all(TEMPLATE_DERIVED_LEAD not in written for _, written in empty)


# --- what it is for -----------------------------------------------------------


def test_the_template_is_a_configuration_document_the_write_path_accepts() -> None:
    """A starting point an operator cannot save is not a starting point."""
    context = OperatingContext(sections=sections_of(template_for(swept())))

    assert len(context.written()) == 5
    assert LXC_METRICS_FACT in context.render()


def test_the_template_fits_inside_the_budget_before_anybody_has_typed_a_word() -> None:
    """Otherwise the first thing the field does is refuse its own suggestion."""
    OperatingContext(sections=sections_of(template_for(swept())))


def test_the_builder_cannot_reach_a_model() -> None:
    """Structural, not a convention. Deriving from the estate and inventing
    something plausible are different claims, and an operator reading the result
    afterwards has no way to tell them apart."""
    source = Path(template_module.__file__).read_text(encoding="utf-8")
    imported = {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not any(name.startswith("core.llm") for name in imported), sorted(imported)
