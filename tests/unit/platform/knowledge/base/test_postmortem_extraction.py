"""What a post-mortem contributes beyond its text, and when a model is asked.

A post-mortem has structure a runbook does not — symptom, what was looked at,
cause, correction, and often "this has happened before". Pulling those out once,
at ingestion, is what makes "has this symptom happened here?" a question the
corpus can answer rather than a paragraph the agent has to read.

Two extractors, tried in that order. The structural one reads headings, is free
and is deterministic. The model is asked only about a document the headings
missed, its answer is cached by the body's checksum so a re-sync costs nothing,
and a deployment with no provider configured still ingests — with the
degradation named in the report rather than silently.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from platform.knowledge.base.models import checksum_of
from platform.knowledge.base.postmortem import (
    EXTRACTED_BY_KEY,
    RECURRED_AS_KEY,
    RECURRENCE_OF_KEY,
    ROOT_CAUSE_KEY,
    SYMPTOM_KEY,
    PostmortemExtractor,
    PostmortemFields,
    extraction_metadata,
    fields_from_metadata,
    structural_fields,
)
from platform.knowledge.base.sync.corpus import CorpusSource

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).resolve().parents[4] / "corpus" / "operational"

JULY_17 = "docs/postmortem/2026-07-17-adguard-dns-stall-both-instances.md"
JULY_20 = "docs/postmortem/2026-07-20-adguard-dns-recurrence-memcg-oom.md"
UNSTRUCTURED = "docs/postmortem/2025-11-08-a-mount-that-would-not-clear.md"


class RecordedModel:
    """A model that answers one structured call from a fixed object.

    Counts its calls, because "a second sync makes no model call" is the whole
    of the caching claim and a mock that only returned a value could not say it.
    """

    provider_id = "recorded"
    model_id = "recorded-extraction"

    def __init__(self, structured: Mapping[str, Any] | None) -> None:
        self.structured = structured
        self.calls = 0

    async def invoke_structured(self, request: Any, schema: Mapping[str, Any]) -> Any:
        """Return the fixed object, counting the call."""
        self.calls += 1
        return _Result(structured=self.structured)


class FailingModel(RecordedModel):
    """A model that is configured and cannot be reached."""

    async def invoke_structured(self, request: Any, schema: Mapping[str, Any]) -> Any:
        """Raise the way an unreachable provider does."""
        self.calls += 1
        raise ConnectionError("no route to the provider")


class _Result:
    """Just enough of an ``InvokeResult`` for the extractor's two reads."""

    def __init__(self, structured: Mapping[str, Any] | None) -> None:
        self.structured = structured
        self.succeeded = structured is not None
        self.failure = None
        self.failure_message = "" if structured is not None else "no object returned"
        self.usage = None


def _body(relative: str) -> str:
    return (CORPUS / relative).read_text(encoding="utf-8")


class TestStructuralExtraction:
    """Headings, and nothing else. Free, and the same answer twice."""

    def test_the_july_seventeen_entry_has_a_symptom_and_no_root_cause(self) -> None:
        found = structural_fields(_body(JULY_17))

        assert "stopped answering queries on both instances" in found.symptom
        assert found.investigation
        assert found.correction
        # It names a section called "Root cause" whose content is that there is
        # none. That is not a root cause, and the corpus must not present it as
        # one — but it is also not nothing, so the text is kept and `explains`
        # is what the ranking reads.
        assert not found.explains

    def test_the_july_twenty_entry_carries_the_cause_the_first_one_missed(self) -> None:
        found = structural_fields(_body(JULY_20))

        assert found.explains
        assert "memory cgroup" in found.root_cause
        assert found.correction

    def test_the_july_twenty_entry_names_what_it_is_a_recurrence_of(self) -> None:
        found = structural_fields(_body(JULY_20))

        assert found.recurrence_of == "2026-07-17-adguard-dns-stall-both-instances"

    def test_every_extracted_field_says_which_section_it_came_from(self) -> None:
        found = structural_fields(_body(JULY_20))

        assert found.sections[SYMPTOM_KEY] == "Symptom"
        assert found.sections[ROOT_CAUSE_KEY] == "Root cause"
        assert found.sections[RECURRENCE_OF_KEY] == "Recurrence of"

    def test_a_document_with_no_headings_yields_nothing(self) -> None:
        found = structural_fields(_body(UNSTRUCTURED))

        assert found.empty
        assert found.extracted_by == ""

    def test_it_is_the_same_answer_twice(self) -> None:
        assert structural_fields(_body(JULY_20)) == structural_fields(_body(JULY_20))


class TestTheMetadataRoundTrip:
    """What is stored is what is read back."""

    def test_fields_survive_the_metadata_bag(self) -> None:
        found = structural_fields(_body(JULY_20))

        assert fields_from_metadata(extraction_metadata(found)) == found

    def test_an_empty_extraction_stores_nothing(self) -> None:
        assert extraction_metadata(PostmortemFields()) == {}

    def test_a_bag_with_nothing_in_it_reads_back_as_nothing(self) -> None:
        assert fields_from_metadata({}).empty
        assert fields_from_metadata({"unrelated": 1}).empty


class TestTheModelFallback:
    """Asked about the documents the headings missed, and only those."""

    @pytest.fixture
    def answer(self) -> Mapping[str, Any]:
        return {
            "symptom": "Every process that touched the backup mount stopped and never returned.",
            "investigation": "The target's address answered while the export was gone.",
            "root_cause": "A firmware update on the target's controller never finished.",
            "correction": "Forced the unmount and brought the controller back by hand.",
        }

    async def test_a_document_the_headings_missed_goes_to_the_model(
        self, answer: Mapping[str, Any]
    ) -> None:
        model = RecordedModel(answer)
        extractor = PostmortemExtractor(llm=model)

        found = await extractor.extract(_body(UNSTRUCTURED), document=UNSTRUCTURED)

        assert model.calls == 1
        assert found.extracted_by == "model"
        assert "firmware update" in found.root_cause

    async def test_a_document_the_headings_read_never_goes_to_the_model(
        self, answer: Mapping[str, Any]
    ) -> None:
        model = RecordedModel(answer)
        extractor = PostmortemExtractor(llm=model)

        found = await extractor.extract(_body(JULY_20), document=JULY_20)

        assert model.calls == 0
        assert found.extracted_by == "structure"

    async def test_the_answer_is_cached_by_checksum_so_a_second_sync_costs_nothing(
        self, answer: Mapping[str, Any]
    ) -> None:
        model = RecordedModel(answer)
        extractor = PostmortemExtractor(llm=model)
        body = _body(UNSTRUCTURED)

        first = await extractor.extract(body, document=UNSTRUCTURED)
        second = await extractor.extract(body, document=UNSTRUCTURED)

        assert model.calls == 1
        assert first == second
        assert checksum_of(body) in extractor.cache

    async def test_an_edited_body_is_a_second_call(self, answer: Mapping[str, Any]) -> None:
        model = RecordedModel(answer)
        extractor = PostmortemExtractor(llm=model)

        await extractor.extract(_body(UNSTRUCTURED), document=UNSTRUCTURED)
        await extractor.extract(
            _body(UNSTRUCTURED) + "\nAnd then it happened again.\n", document=UNSTRUCTURED
        )

        assert model.calls == 2


class TestDegradingWithoutAProvider:
    """Structural only, and the report says so."""

    async def test_no_provider_leaves_the_structural_answer_and_names_the_degradation(
        self,
    ) -> None:
        extractor = PostmortemExtractor(llm=None)

        found = await extractor.extract(_body(UNSTRUCTURED), document=UNSTRUCTURED)

        assert found.empty
        assert extractor.degradations == (
            f"{UNSTRUCTURED}: no model is configured for the extraction role, so this "
            f"post-mortem was read for its headings alone and has none.",
        )

    async def test_the_structural_answer_still_stands_for_a_document_that_has_headings(
        self,
    ) -> None:
        extractor = PostmortemExtractor(llm=None)

        found = await extractor.extract(_body(JULY_20), document=JULY_20)

        assert found.explains
        assert extractor.degradations == ()

    async def test_a_provider_that_cannot_be_reached_is_a_degradation_and_never_an_error(
        self,
    ) -> None:
        model = FailingModel(None)
        extractor = PostmortemExtractor(llm=model)

        found = await extractor.extract(_body(UNSTRUCTURED), document=UNSTRUCTURED)

        assert found.empty
        assert len(extractor.degradations) == 1
        assert "ConnectionError" in extractor.degradations[0]


class TestBothDirectionsOfARecurrence:
    """The pair is stored from each end, so either one leads to the other."""

    @pytest.fixture
    def corpus(self, tmp_path: Path) -> Path:
        root = tmp_path / "infra"
        shutil.copytree(CORPUS, root)
        return root

    async def test_the_later_entry_points_back_and_the_earlier_one_points_forward(
        self, corpus: Path
    ) -> None:
        found = await _fetched(corpus)

        assert found[JULY_20].metadata[RECURRENCE_OF_KEY] == JULY_17
        assert found[JULY_17].metadata[RECURRED_AS_KEY] == [JULY_20]

    async def test_the_extraction_is_recorded_on_the_document_it_came_from(
        self, corpus: Path
    ) -> None:
        found = await _fetched(corpus)

        assert found[JULY_20].metadata[EXTRACTED_BY_KEY] == "structure"
        assert "memory cgroup" in found[JULY_20].metadata[ROOT_CAUSE_KEY]

    async def test_a_document_that_is_not_a_postmortem_carries_no_extraction(
        self, corpus: Path
    ) -> None:
        found = await _fetched(corpus)

        assert found["docs/runbooks/adguard-dns-recovery.md"].metadata == {}
        assert found["policies/firewall/cluster.yaml"].metadata == {}

    async def test_a_recurrence_naming_a_document_the_corpus_does_not_hold_is_left_as_written(
        self, corpus: Path
    ) -> None:
        (corpus / JULY_17).unlink()

        found = await _fetched(corpus)

        assert (
            found[JULY_20].metadata[RECURRENCE_OF_KEY]
            == "2026-07-17-adguard-dns-stall-both-instances"
        )


async def _fetched(root: Path) -> Mapping[str, Any]:
    """Return the corpus's documents by path, with extraction applied."""
    source = CorpusSource(root=root, extractor=PostmortemExtractor(llm=None))
    documents: Sequence[Any] = await source.fetch()
    return {entry.external_id: entry for entry in documents}
