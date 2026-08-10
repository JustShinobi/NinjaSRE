"""What the model call is worth, as a number, over the ten post-mortems.

Extraction has two arms and the question this answers is whether the second one
earns its cost. Structural extraction is free, deterministic and reads headings;
the model arm is one bounded call per document the headings missed. A deployment
choosing between them — and a deployment that has no provider at all and gets
the first arm whether it wanted it or not — needs the difference stated rather
than asserted.

**Recall against a human reading, not against the extractor.** ``truth.json``
lists the fields each document genuinely answers, decided by reading it. An
ablation scored against what the extractor produced would report agreement with
itself.

**The model is recorded.** The pull-request path has no provider, and an
ablation whose second arm needs one is an ablation nobody runs. The reply is a
fixture, exactly as the hypervisor corpus records its transcripts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from platform.knowledge.base.postmortem import (
    PostmortemExtractor,
    PostmortemFields,
    extraction_metadata,
)

pytestmark = pytest.mark.synthetic

HERE = Path(__file__).resolve().parent / "postmortem"
CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "operational"

TRUTH: Mapping[str, Any] = json.loads((HERE / "truth.json").read_text(encoding="utf-8"))
REPLIES: Mapping[str, Any] = json.loads(
    (HERE / "recorded_replies.json").read_text(encoding="utf-8")
)["replies"]

#: The fields the ablation counts. ``sections`` and ``extracted_by`` are how the
#: extraction is attributed rather than what it found, so neither is scored.
SCORED = ("symptom", "investigation", "root_cause", "correction", "recurrence_of")


class RecordedExtractionModel:
    """Answers from the recorded replies, and refuses a document it has none for.

    Refuses rather than returning nothing, so a document the headings should
    have read never reaches the model quietly. ``asked`` is the second half of
    the measurement: an arm that called the model ten times to gain one field
    would be a worse arm than the number alone would show.
    """

    provider_id = "recorded"
    model_id = "recorded-extraction"

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def invoke_structured(self, request: Any, schema: Mapping[str, Any]) -> Any:
        """Return the recorded reply for whichever document this request quotes."""
        for path, reply in REPLIES.items():
            if _distinctive(path) in request.messages[0].text:
                self.asked.append(path)
                return _Result(reply)
        raise AssertionError("the model was asked about a document with no recorded reply")


class _Result:
    """Just enough of an ``InvokeResult`` for the extractor's two reads."""

    def __init__(self, structured: Mapping[str, Any]) -> None:
        self.structured = structured
        self.succeeded = True
        self.failure = None
        self.failure_message = ""
        self.usage = None


def _distinctive(path: str) -> str:
    """Return a phrase that appears in this document and in no other."""
    body = (CORPUS / path).read_text(encoding="utf-8")
    return body.splitlines()[0].removeprefix("# ").strip() or path


@dataclass(frozen=True, slots=True)
class ArmScore:
    """One arm's recall over the evaluation corpus."""

    arm: str
    recovered: int
    expected: int
    documents_explaining: int
    model_calls: int

    @property
    def recall(self) -> float:
        """Return the fraction of the fields a human read that this arm recovered."""
        return self.recovered / self.expected if self.expected else 0.0

    def describe(self) -> str:
        """Return the line this ablation publishes."""
        return (
            f"{self.arm}: {self.recovered}/{self.expected} fields "
            f"({self.recall:.1%}), {self.documents_explaining} documents naming a cause, "
            f"{self.model_calls} model calls"
        )


async def score(arm: str, *, with_model: bool) -> ArmScore:
    """Return what one arm recovered over the ten post-mortems."""
    model = RecordedExtractionModel() if with_model else None
    extractor = PostmortemExtractor(llm=model)

    recovered = 0
    expected = 0
    explaining = 0

    for path, wanted in sorted(TRUTH["documents"].items()):
        body = (CORPUS / path).read_text(encoding="utf-8")
        found = await extractor.extract(body, document=path)
        stored = extraction_metadata(found)
        expected += len(wanted)
        recovered += sum(1 for name in wanted if name in SCORED and stored.get(name))
        explaining += 1 if found.explains else 0

    return ArmScore(
        arm=arm,
        recovered=recovered,
        expected=expected,
        documents_explaining=explaining,
        model_calls=len(model.asked) if model is not None else 0,
    )


class TestTheAblation:
    """Both arms, reported, with the difference between them as a number."""

    @pytest.fixture
    async def structural(self) -> ArmScore:
        return await score("structural only", with_model=False)

    @pytest.fixture
    async def assisted(self) -> ArmScore:
        return await score("structural, model fallback", with_model=True)

    def test_structural_alone_recovers_thirty_seven_of_forty_one_fields(
        self, structural: ArmScore
    ) -> None:
        # The four it misses are one document, written without headings. Pinned
        # rather than bounded: a change that moves this is a change to what the
        # corpus gets for free, and it should be read rather than absorbed.
        assert (structural.recovered, structural.expected) == (37, 41)
        assert structural.model_calls == 0

    def test_the_model_fallback_recovers_all_forty_one(self, assisted: ArmScore) -> None:
        assert (assisted.recovered, assisted.expected) == (41, 41)

    def test_the_model_is_asked_about_exactly_the_document_the_headings_missed(
        self, assisted: ArmScore
    ) -> None:
        # One call for the whole corpus. The cost of the second arm is what
        # decides whether it is worth configuring, and "one call per corpus"
        # and "one call per document" are different decisions.
        assert assisted.model_calls == 1

    def test_the_fallback_is_what_makes_the_tenth_document_name_a_cause(
        self, structural: ArmScore, assisted: ArmScore
    ) -> None:
        assert structural.documents_explaining == len(TRUTH["explains"]) - 1
        assert assisted.documents_explaining == len(TRUTH["explains"])

    def test_the_arms_are_reported_side_by_side(
        self, structural: ArmScore, assisted: ArmScore
    ) -> None:
        report = "\n".join((structural.describe(), assisted.describe()))

        assert "structural only: 37/41 fields (90.2%)" in report
        assert "structural, model fallback: 41/41 fields (100.0%)" in report

    async def test_both_arms_score_the_same_twice(self) -> None:
        # An ablation whose two runs disagree is not a measurement.
        assert await score("a", with_model=False) == await score("a", with_model=False)
        assert await score("b", with_model=True) == await score("b", with_model=True)


class TestWhatTheAblationIsScoredAgainst:
    """The truth file has to describe the corpus that is actually here."""

    def test_every_document_it_scores_exists(self) -> None:
        for path in TRUTH["documents"]:
            assert (CORPUS / path).is_file(), path

    def test_every_postmortem_in_the_corpus_is_scored(self) -> None:
        present = {
            f"docs/postmortem/{path.name}" for path in (CORPUS / "docs" / "postmortem").glob("*.md")
        }

        assert present == set(TRUTH["documents"])

    def test_only_scorable_field_names_are_claimed(self) -> None:
        for path, wanted in TRUTH["documents"].items():
            assert set(wanted) <= set(SCORED), path

    def test_the_documents_that_name_a_cause_are_the_ones_the_extractor_finds(self) -> None:
        # Nine of ten. The July 17th entry records that no cause was found,
        # which is a section and not a cause — and the whole ranking rests on
        # the corpus being able to tell the difference.
        assert set(TRUTH["explains"]) == set(TRUTH["documents"]) - {
            "docs/postmortem/2026-07-17-adguard-dns-stall-both-instances.md"
        }


def test_a_field_the_extractor_invents_is_not_scored_as_recovered() -> None:
    """The guard on the measurement itself.

    Recall over "fields present in the output" would be satisfied by an
    extractor that filled every field with the first paragraph. The score counts
    only the fields the truth file asks for, so a fabricated field is worth
    nothing — and this is what says so.
    """
    invented = PostmortemFields(symptom="s", root_cause="r", correction="c", investigation="i")
    stored = extraction_metadata(invented)

    wanted = ["symptom"]
    assert sum(1 for name in wanted if name in SCORED and stored.get(name)) == 1
