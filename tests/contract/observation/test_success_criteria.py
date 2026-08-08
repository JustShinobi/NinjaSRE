"""Every claim this feature makes, against the named test that proves it.

A list of claims in a document goes stale silently: the test that backed one
gets renamed in a refactor, the document keeps saying it is proven, and nobody
finds out. A list of claims in a *test* fails the build instead, which is the
whole reason this file exists rather than a table in a specification a
contributor cloning the repository does not have.

Each row names the claim in the operator's terms and the test that holds it. The
claims are stated here in full so that somebody reading this file learns what
the feature promised without having to find the specification it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

pytestmark = pytest.mark.contract

REPO_ROOT: Final = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class Claim:
    """One thing continuous observation claims, and where it is proven."""

    claim: str
    #: Repository-relative path of the test module.
    module: str
    #: The test function's name, verbatim.
    test: str


CLAIMS: Final[tuple[Claim, ...]] = (
    Claim(
        claim=(
            "A condition crossing and holding opens exactly one incident, and a "
            "condition crossing and recovering inside the duration opens none."
        ),
        module="tests/unit/platform/incidents/test_incident_lifecycle.py",
        test="test_a_condition_crossing_and_holding_opens_exactly_one_incident",
    ),
    Claim(
        claim="A condition that recovers inside its duration opens nothing at all.",
        module="tests/unit/platform/incidents/test_incident_lifecycle.py",
        test="test_a_condition_crossing_and_recovering_inside_the_duration_opens_none",
    ),
    Claim(
        claim="The same condition firing repeatedly correlates to one incident.",
        module="tests/unit/platform/incidents/test_incident_lifecycle.py",
        test="test_the_same_condition_firing_again_correlates_rather_than_opening_a_second",
    ),
    Claim(
        claim=(
            "A recovered condition self-closes its incident after the recovery "
            "duration, and says it self-resolved."
        ),
        module="tests/unit/platform/incidents/test_incident_lifecycle.py",
        test="test_a_recovered_condition_closes_its_incident_and_says_it_self_resolved",
    ),
    Claim(
        claim="A firing inside a maintenance window is suppressed and recorded as suppressed.",
        module="tests/unit/platform/observation/test_suppression.py",
        test="test_a_firing_inside_a_maintenance_window_is_recorded_as_suppressed",
    ),
    Claim(
        claim="One cause across fifty resources produces one incident with fifty subjects.",
        module="tests/unit/platform/incidents/test_incident_lifecycle.py",
        test="test_one_cause_across_fifty_resources_is_one_incident_with_fifty_subjects",
    ),
    Claim(
        claim=(
            "A webhook alert and a detected condition produce structurally identical "
            "incidents, asserted field by field."
        ),
        module="tests/contract/observation/test_one_incident_whatever_raised_it.py",
        test="test_a_webhook_alert_and_a_detected_condition_are_structurally_identical",
    ),
    Claim(
        claim="A failing detector surfaces as an attention item rather than being skipped.",
        module="tests/unit/platform/incidents/test_incident_lifecycle.py",
        test="test_a_failing_detector_becomes_its_own_incident",
    ),
    Claim(
        claim="Restart mid-evaluation does not double-fire.",
        module="tests/unit/platform/observation/test_evaluation.py",
        test="test_a_second_tick_over_the_same_signals_reaches_the_same_verdicts",
    ),
    Claim(
        claim="Two replicas evaluating at one instant produce one outcome.",
        module="tests/unit/platform/observation/test_evaluation.py",
        test="test_two_replicas_evaluating_the_same_instant_produce_one_outcome",
    ),
    Claim(
        claim=(
            "A detector replayed against historical signals reproduces exactly the "
            "firings that happened."
        ),
        module="tests/unit/platform/observation/test_evaluation.py",
        test="test_a_detector_replayed_against_history_reproduces_exactly_what_happened",
    ),
    Claim(
        claim=(
            "Ten thousand resources and one hundred detectors evaluate inside the declared budget."
        ),
        module="tests/benchmarks/test_observation_scale.py",
        test="test_one_tick_over_ten_thousand_resources_stays_inside_its_budget",
    ),
    Claim(
        claim="Exactly one lifecycle constructs an incident, whatever raised it.",
        module="tests/architecture/test_one_incident_lifecycle.py",
        test="test_exactly_one_module_constructs_an_incident",
    ),
    Claim(
        claim="A flapping signal reports flapping rather than firing per crossing.",
        module="tests/unit/platform/observation/test_detector_rules.py",
        test="test_a_flapping_signal_reports_flapping_rather_than_firing_per_crossing",
    ),
    Claim(
        claim="A signal that stopped arriving is distinguishable from one reporting healthily.",
        module="tests/unit/platform/observation/test_signal_sources.py",
        test="test_a_series_that_stopped_is_distinguishable_from_one_reporting_healthily",
    ),
    Claim(
        claim="A detector may not reference a capability that is anything but read-only.",
        module="tests/unit/platform/observation/test_detector_rules.py",
        test="test_a_detector_may_not_reference_a_capability_that_writes",
    ),
    Claim(
        claim="A team declares a detector through configuration, and inheritance applies.",
        module="tests/contract/observation/test_detectors_from_configuration.py",
        test="test_a_detector_written_at_a_division_reaches_the_team",
    ),
    Claim(
        claim="A hundred simultaneous incidents do not start a hundred simultaneous runs.",
        module="tests/unit/platform/incidents/test_dispatch_and_escalation.py",
        test="test_a_hundred_simultaneous_incidents_do_not_start_a_hundred_runs",
    ),
    Claim(
        claim="Escalation stops the moment the incident closes.",
        module="tests/unit/platform/incidents/test_dispatch_and_escalation.py",
        test="test_escalation_stops_when_the_incident_closes",
    ),
    Claim(
        claim=(
            "A maintenance window spanning a daylight-saving change lasts as long as "
            "it was declared to."
        ),
        module="tests/unit/platform/observation/test_suppression.py",
        test="test_a_window_spanning_a_daylight_saving_change_lasts_as_long_as_declared",
    ),
)


@pytest.mark.parametrize("claim", CLAIMS, ids=[entry.test for entry in CLAIMS])
def test_every_claim_is_held_by_a_test_that_exists(claim: Claim) -> None:
    """A proof that was renamed fails here rather than quietly covering nothing."""
    module = REPO_ROOT / claim.module
    assert module.exists(), f"{claim.module} does not exist; it holds: {claim.claim}"

    source = module.read_text(encoding="utf-8")
    assert re.search(rf"^(async )?def {re.escape(claim.test)}\(", source, re.M), (
        f"{claim.module} no longer defines {claim.test}, which is what holds: {claim.claim}"
    )


def test_no_claim_names_the_same_test_twice() -> None:
    """One test holding two claims means one of them is not really tested."""
    named = [claim.test for claim in CLAIMS]

    assert len(set(named)) == len(named), "two claims point at the same test"
