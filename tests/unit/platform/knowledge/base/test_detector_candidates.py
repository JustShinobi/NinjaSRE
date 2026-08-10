"""The checks an experienced operator already runs, proposed as detectors.

``cluster-double-check-queries.md`` is a list of verifications somebody wrote
down because each of them has caught something. Every one is a detector that
does not exist yet, and the gap between "written down" and "watched
continuously" is the whole of why an estate has a problem nobody noticed.

**Proposed, never enabled.** A document turning itself into something that pages
people is the one thing this must not do. Each candidate arrives disabled, with
the sentence its author wrote attached, and enabling it is an operator's act —
previewed with the dry run that already exists.

**Ordinary detector rows.** Not a parallel queue: the detectors surface, the
dry run, and the enable and disable routes all exist, and a second store would
need its own of each to buy nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.constants.knowledge import (
    MAX_DETECTOR_CANDIDATES,
    MAX_DETECTOR_ORIGIN_EXCERPT_CHARS,
)
from platform.config_service.schema.policies import DetectorSettings, ObservationPolicySettings
from platform.knowledge.base.detector_candidates import (
    CANDIDATE_ID_PREFIX,
    DetectorCandidate,
    candidates_from,
)
from platform.observation.detectors.config import read as read_detectors

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).resolve().parents[4] / "corpus" / "operational"
QUERIES = "docs/runbooks/cluster-double-check-queries.md"
DOCUMENT_ID = f"corpus:{QUERIES}"


def _body() -> str:
    return (CORPUS / QUERIES).read_text(encoding="utf-8")


def _found() -> tuple[DetectorCandidate, ...]:
    return candidates_from(_body(), document_id=DOCUMENT_ID, location=QUERIES)


class TestReadingTheDocument:
    """One candidate per verification the document states a number for."""

    def test_every_check_with_a_signal_and_a_threshold_becomes_a_candidate(self) -> None:
        assert [candidate.detector_id for candidate in _found()] == [
            f"{CANDIDATE_ID_PREFIX}quorum-margin-is-above-zero",
            f"{CANDIDATE_ID_PREFIX}no-datastore-is-above-its-safe-fill",
            f"{CANDIDATE_ID_PREFIX}no-backup-is-older-than-its-schedule",
            f"{CANDIDATE_ID_PREFIX}no-node-is-reporting-failed-units",
            f"{CANDIDATE_ID_PREFIX}no-mount-is-stalled",
        ]

    def test_a_candidate_carries_the_signal_and_the_number_the_author_wrote(self) -> None:
        quorum = _found()[0]

        assert quorum.signal == "cluster.quorum_margin"
        assert quorum.comparison == "below"
        assert quorum.fire_value == 1.0

    def test_a_candidate_is_named_by_the_heading_it_came_from(self) -> None:
        assert _found()[0].name == "Quorum margin is above zero"

    def test_a_candidate_quotes_the_reason_its_author_gave(self) -> None:
        quorum = _found()[0]

        assert "the next node to leave takes the cluster with it" in quorum.origin_excerpt
        assert len(quorum.origin_excerpt) <= MAX_DETECTOR_ORIGIN_EXCERPT_CHARS

    def test_a_candidate_cites_the_document_it_came_from(self) -> None:
        quorum = _found()[0]

        assert quorum.origin == DOCUMENT_ID
        assert quorum.location == QUERIES

    def test_a_document_stating_no_numbers_proposes_nothing(self) -> None:
        body = "# Notes\n\n## Check the thing\n\nHave a look at it now and then.\n"

        assert candidates_from(body, document_id="d", location="d.md") == ()

    def test_reading_it_twice_gives_the_same_answer(self) -> None:
        assert _found() == _found()

    def test_the_number_of_candidates_one_document_may_propose_is_bounded(self) -> None:
        sections = "".join(
            f"\n## Check {ordinal}\n\n- signal: `s.{ordinal}`\n- fires when: above {ordinal}\n"
            for ordinal in range(MAX_DETECTOR_CANDIDATES + 5)
        )

        assert len(candidates_from(sections, document_id="d", location="d.md")) == (
            MAX_DETECTOR_CANDIDATES
        )


class TestWhatACandidateBecomes:
    """A detector row the existing surface already knows how to render."""

    def test_it_settles_into_the_declaration_the_config_schema_builds(self) -> None:
        settings = ObservationPolicySettings(
            detectors=[DetectorSettings(**candidate.to_settings()) for candidate in _found()]
        )

        resolved = read_detectors(settings)

        assert resolved.problems == ()
        assert len(resolved.detectors) == 5

    def test_every_one_of_them_is_disabled(self) -> None:
        settings = ObservationPolicySettings(
            detectors=[DetectorSettings(**candidate.to_settings()) for candidate in _found()]
        )

        resolved = read_detectors(settings)

        assert all(not declaration.enabled for declaration in resolved.detectors)
        # Which is what makes it true that nothing fires: the enabled set is
        # what a tick evaluates, and it is empty.
        assert resolved.enabled == ()

    def test_the_declaration_still_names_the_document_it_came_from(self) -> None:
        settings = ObservationPolicySettings(
            detectors=[DetectorSettings(**_found()[0].to_settings())]
        )

        declaration = read_detectors(settings).detectors[0]

        assert declaration.origin == DOCUMENT_ID
        assert "the next node to leave takes the cluster with it" in declaration.origin_excerpt

    def test_a_shipped_detector_has_no_origin_and_is_therefore_not_a_candidate(self) -> None:
        settings = ObservationPolicySettings(
            detectors=[
                DetectorSettings(detector_id="node-load", signal="node.load", fire_value=8.0)
            ]
        )

        declaration = read_detectors(settings).detectors[0]

        assert declaration.origin == ""
        assert declaration.enabled
