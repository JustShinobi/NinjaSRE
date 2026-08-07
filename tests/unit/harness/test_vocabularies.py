"""T005: the vocabularies a fixture is checked against, and where they come from.

Two of the four are closed sets written down here, because a failure mode and
an adversarial signal are properties of the *incident* and nothing in the
repository declares them. The other two are read from the running system: root
causes from the taxonomy, trajectory actions from the capability catalogue.

That second pair is the whole point. A scenario whose answer key names
``list_pods`` after somebody renamed the capability to
``kubernetes_workload_pods`` would otherwise keep scoring — badly, silently,
and in a way that looks like the agent got worse.
"""

from __future__ import annotations

import pytest

from capabilities.registry.catalogue import build_registry
from core.domain.diagnosis.taxonomy import ROOT_CAUSE_CATEGORIES
from tests.harness.vocabularies import (
    ADVERSARIAL_SIGNALS,
    FAILURE_MODES,
    SEVERITIES,
    TRAJECTORY_MATCHINGS,
    evidence_sources,
    root_cause_categories,
    trajectory_actions,
)

pytestmark = pytest.mark.unit


def test_the_trajectory_vocabulary_is_the_live_capability_catalogue() -> None:
    """A renamed capability is a load error, not a silent scoring failure."""
    registry = build_registry()

    assert trajectory_actions() >= set(registry.tools)
    assert "kubernetes_workload_events" in trajectory_actions()


def test_a_renamed_capability_leaves_its_old_name_outside_the_vocabulary() -> None:
    assert "list_pods" not in trajectory_actions()


def test_the_root_cause_vocabulary_is_the_shipped_taxonomy() -> None:
    assert root_cause_categories() == {found.value for found in ROOT_CAUSE_CATEGORIES}


def test_every_integration_in_the_repository_is_an_evidence_source() -> None:
    """SC-005: a new integration's scenario needs no vocabulary edit."""
    from integrations._catalogue.discovery import catalogue

    names = {entry.name for entry in catalogue()}

    assert names <= evidence_sources()


def test_the_reasoning_sources_that_belong_to_no_vendor_are_evidence_sources_too() -> None:
    assert {"reasoning", "memory", "knowledge_base"} <= evidence_sources()


def test_the_closed_vocabularies_are_non_empty_and_lower_snake_case() -> None:
    for vocabulary in (FAILURE_MODES, ADVERSARIAL_SIGNALS, SEVERITIES, TRAJECTORY_MATCHINGS):
        assert vocabulary
        for term in vocabulary:
            assert term == term.lower()
            assert " " not in term
