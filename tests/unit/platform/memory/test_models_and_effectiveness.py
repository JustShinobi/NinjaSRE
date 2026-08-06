"""The episode model, and the formula that decides how good a run was.

Two properties are asserted here that the rest of the feature depends on and
that nothing else would catch.

**The round trip is lossless.** An episode goes to the storage shape and back
unchanged. The storage shape is narrow — a title, a summary, an outcome, a JSON
payload — so every typed field is either a column or a payload key, and a field
added to the model without a home in the payload disappears silently on the way
to the database and comes back as a default. This is what makes that loud.

**The formula is monotonic and bounded.** Effectiveness feeds ranking, ranking
changes agent behaviour, and a formula that could return 1.4 or that scored a
worse run higher would do so quietly, on every episode, until somebody looked.
"""

from __future__ import annotations

import pytest

from capabilities.tools.system.memory_search.results import OUTCOME_RESOLVED
from config.constants.memory import (
    EFFECTIVENESS_FORMULA_VERSION,
    MAX_EPISODE_COMPONENTS,
    MAX_EPISODE_SUMMARY_CHARS,
)
from config.prompts.memory import EPISODE_EXTRACTION_SYSTEM_PROMPT
from platform.memory import models
from platform.memory.effectiveness import (
    EffectivenessInputs,
    effectiveness,
    evidence_backing_ratio,
    formula_version,
    trajectory_efficiency,
)
from platform.memory.models import (
    Component,
    EpisodeSeverity,
    KeyFinding,
    MemoryEpisode,
    ScoredEpisode,
)
from platform.persistence.ports.episode_store import EpisodeOutcome
from tests.unit.platform.memory.conftest import PAYMENTS_TEAM, PRIMARY_ORG, at

pytestmark = pytest.mark.unit


def episode(**overrides: object) -> MemoryEpisode:
    """Return a complete episode, with any field replaced."""
    fields: dict[str, object] = {
        "correlation_id": "conv-1",
        "org_id": PRIMARY_ORG,
        "team_node_id": PAYMENTS_TEAM,
        "issue_type": "oom_kill",
        "issue_description": "payments-api restarting with exit code 137",
        "severity": EpisodeSeverity.HIGH,
        "components": (Component(type="service", name="payments-api"),),
        "capabilities_used": ("describe_workload", "read_logs"),
        "key_findings": (
            KeyFinding(
                capability="describe_workload",
                query="payments-api",
                finding="last state OOMKilled",
            ),
        ),
        "resolved": True,
        "root_cause": "the 02:50 deploy lowered the memory limit",
        "summary": "A deploy lowered the container memory limit and every pod OOMKilled.",
        "effectiveness_score": 0.82,
        "duration_seconds": 312.0,
        "iterations": 4,
        "run_id": "run-1",
        "occurred_at": at(),
        "updated_at": at(0.01),
        "embedding_model": "ninjasre-local-hash-v1",
        "embedding_dimension": 256,
    }
    fields.update(overrides)
    return MemoryEpisode(**fields)  # type: ignore[arg-type]


# -- the model ----------------------------------------------------------------


def test_component_parses_back_to_what_it_rendered() -> None:
    """A component survives the flat label the storage layer holds it as."""
    original = Component(type="Deployment", name="payments-api")

    assert original.label == "deployment:payments-api"
    assert Component.parse(original.label) == original


def test_a_bare_label_is_a_component_of_unstated_type() -> None:
    """An episode written before types were extracted is still matchable."""
    parsed = Component.parse("payments-api")

    assert parsed.name == "payments-api"
    assert parsed.type == ""


def test_an_episode_round_trips_through_the_storage_shape() -> None:
    """Every typed field survives the narrow row and its JSON payload."""
    original = episode()

    restored = MemoryEpisode.from_stored(original.to_stored(), org_id=PRIMARY_ORG)

    assert restored == original


def test_resolved_maps_to_the_stored_outcome_and_back() -> None:
    """``resolved`` is the flag; the stored outcome is its projection."""
    assert episode(resolved=True).to_stored().outcome is EpisodeOutcome.RESOLVED
    assert episode(resolved=False).to_stored().outcome is EpisodeOutcome.INCONCLUSIVE


def test_resolved_never_claims_production_was_fixed() -> None:
    """FR-003 is documented wherever the flag surfaces, starting here.

    Asserted rather than trusted: the meaning of this flag is stated in the
    model, the extraction prompt, and the shaped recall result, and the whole
    point of stating it three times is that all three keep saying it.
    """
    assert "does not mean production was fixed" in (models.__doc__ or "")
    assert "NOT mean production was fixed" in EPISODE_EXTRACTION_SYSTEM_PROMPT
    assert "root cause established" in OUTCOME_RESOLVED


def test_an_episode_must_carry_an_organisation_and_a_team() -> None:
    """An unscoped episode is one every team could retrieve."""
    with pytest.raises(ValueError, match="organisation and a team"):
        episode(team_node_id="")


def test_the_embedding_text_is_the_four_documented_fields() -> None:
    """FR-016: issue type, description, summary, and root cause — not the findings.

    Findings are long and full of identifiers, and embedding them makes two
    unrelated incidents on one cluster look similar for naming the same nodes.
    """
    text = episode().embedding_text()

    assert "oom_kill" in text
    assert "exit code 137" in text
    assert "lowered the memory limit" in text
    assert "last state OOMKilled" not in text


def test_the_signature_is_stable_and_depends_on_type_and_components() -> None:
    """Two runs of the same failure on the same service fingerprint alike."""
    first = episode(correlation_id="conv-1")
    second = episode(correlation_id="conv-2")
    different = episode(issue_type="certificate_expiry")

    assert first.signature() == second.signature()
    assert first.signature() != different.signature()


def test_merging_a_second_turn_keeps_both_turns_capabilities_in_order() -> None:
    """A repeat turn updates the episode without forgetting the first turn's trajectory."""
    first = episode(capabilities_used=("describe_workload", "read_logs"))
    second = episode(capabilities_used=("read_logs", "deploy_history"))

    merged = second.merged_with(first)

    assert merged.capabilities_used == ("describe_workload", "read_logs", "deploy_history")


def test_oversized_content_is_bounded_rather_than_stored() -> None:
    """A very long investigation cannot write an unbounded episode."""
    bounded = episode(
        summary="x" * (MAX_EPISODE_SUMMARY_CHARS * 2),
        components=tuple(
            Component(type="service", name=f"svc-{index}")
            for index in range(MAX_EPISODE_COMPONENTS * 2)
        ),
    )

    assert len(bounded.summary) == MAX_EPISODE_SUMMARY_CHARS
    assert len(bounded.components) == MAX_EPISODE_COMPONENTS


def test_vector_metadata_carries_the_team_the_filter_runs_on() -> None:
    """The cheap half of FR-023 is a metadata equality filter, so it has to be written."""
    metadata = episode().vector_metadata()

    assert metadata["team_node_id"] == PAYMENTS_TEAM
    assert metadata["resolved"] is True
    assert metadata["issue_type"] == "oom_kill"


def test_a_scored_episode_exposes_every_term_of_its_rank() -> None:
    """An operator asking why this ranked first gets an answer, not a number."""
    terms = ScoredEpisode(episode=episode(), similarity=0.9, score=0.7).terms()

    assert set(terms) == {
        "similarity",
        "resolved",
        "component_overlap",
        "effectiveness",
        "recency",
    }


# -- the formula --------------------------------------------------------------


def test_effectiveness_is_bounded_to_the_unit_interval() -> None:
    """The weights sum to one, so the score cannot leave [0, 1] — proved at both ends."""
    worst = effectiveness(
        EffectivenessInputs(
            resolved=False, has_root_cause=False, validated_claims=0, total_claims=10, iterations=99
        )
    )
    best = effectiveness(
        EffectivenessInputs(
            resolved=True, has_root_cause=True, validated_claims=10, total_claims=10, iterations=1
        )
    )

    assert 0.0 <= worst < best <= 1.0


@pytest.mark.parametrize(
    ("weaker", "stronger"),
    [
        (
            EffectivenessInputs(resolved=False, has_root_cause=True, iterations=4),
            EffectivenessInputs(resolved=True, has_root_cause=True, iterations=4),
        ),
        (
            EffectivenessInputs(resolved=True, has_root_cause=False, iterations=4),
            EffectivenessInputs(resolved=True, has_root_cause=True, iterations=4),
        ),
        (
            EffectivenessInputs(validated_claims=2, total_claims=10, iterations=4),
            EffectivenessInputs(validated_claims=8, total_claims=10, iterations=4),
        ),
        (
            EffectivenessInputs(iterations=20),
            EffectivenessInputs(iterations=3),
        ),
    ],
    ids=["resolved", "root_cause", "evidence_backing", "trajectory"],
)
def test_effectiveness_is_monotonic_in_each_term(
    weaker: EffectivenessInputs, stronger: EffectivenessInputs
) -> None:
    """Improving one input and holding the rest cannot lower the score."""
    assert effectiveness(weaker) < effectiveness(stronger)


def test_a_run_that_claimed_nothing_scores_no_evidence_backing() -> None:
    """Vacuous perfection would outrank a run that concluded something and backed it."""
    assert evidence_backing_ratio(0, 0) == 0.0
    assert evidence_backing_ratio(3, 4) == 0.75


def test_trajectory_efficiency_is_a_bounded_inverse_not_a_cliff() -> None:
    """A run at the reference is perfect; twice the reference is half, not zero."""
    assert trajectory_efficiency(0) == 1.0
    assert trajectory_efficiency(5) == 1.0
    assert trajectory_efficiency(10) == pytest.approx(0.5)
    assert trajectory_efficiency(1_000) > 0.0


def test_a_claim_cannot_be_backed_without_having_been_made() -> None:
    """More validated claims than total claims is arithmetic nobody meant."""
    with pytest.raises(ValueError, match="cannot be backed"):
        EffectivenessInputs(validated_claims=5, total_claims=2)


def test_the_formula_version_is_the_one_stamped_onto_episodes() -> None:
    """A weight change without a version bump reinterprets the whole corpus."""
    assert formula_version() == EFFECTIVENESS_FORMULA_VERSION
    assert episode().effectiveness_formula_version == EFFECTIVENESS_FORMULA_VERSION
