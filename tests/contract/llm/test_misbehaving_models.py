"""Every recorded misbehaviour, replayed into the layer that handles it.

This is the suite that makes "testable against a recorded transcript, without a
live model" a fact rather than an intention. Each test names the file it drives,
so a failure points at a recording somebody can open and read.

The last test in the file is the one that keeps the set honest: every transcript
under ``transcripts/`` has to be driven by something here, so adding a recorded
misbehaviour and forgetting to assert anything about it fails the build.
"""

from __future__ import annotations

import pytest
from conftest import RecordedTransport, build_client

from config.constants.llm import MAX_IDENTICAL_CALLS_IN_WINDOW, PROVIDER_OLLAMA
from core.agent.result_truncation import truncate_for_model
from core.llm.failures import ErrorObservation, FailureClass, classify
from core.llm.probe import ModelLimits
from core.llm.types import InvokeRequest, Message, RepairKind, Role, StreamEventKind
from tests.support.misbehaviour import (
    MODEL_ID,
    expected_sequence,
    load,
    replay,
    streamed_events,
    transcript_ids,
)

#: Every transcript this file drives. Kept beside the tests rather than derived,
#: so the coverage assertion at the bottom compares two independent lists.
DRIVEN = {
    "tool_call_as_text",
    "tool_call_in_fenced_json",
    "out_of_schema_argument",
    "missing_required_argument",
    "fragmented_streamed_call",
    "two_calls_where_one_expected",
    "identical_repeated_calls",
    "oversized_capability_result",
    "success_with_error_body",
    "unparseable_arguments",
}


class TestACallWrittenAsText:
    async def test_a_bare_json_call_is_extracted_and_recorded_as_a_repair(self) -> None:
        transcript = load("tool_call_as_text")

        outcome = await replay(transcript)

        assert outcome.repairs == (RepairKind.TOOL_CALL_EXTRACTED.value,)
        assert [
            {"name": call.name, "arguments": dict(call.arguments)}
            for call in outcome.final.tool_calls
        ] == expected_sequence(transcript)

    async def test_a_fenced_call_in_the_other_spelling_is_extracted(self) -> None:
        transcript = load("tool_call_in_fenced_json")

        outcome = await replay(transcript)

        assert outcome.repairs == (RepairKind.TOOL_CALL_EXTRACTED.value,)
        assert [
            {"name": call.name, "arguments": dict(call.arguments)}
            for call in outcome.final.tool_calls
        ] == expected_sequence(transcript)

    async def test_an_unreadable_call_is_refused_and_the_model_is_told_which(self) -> None:
        transcript = load("unparseable_arguments")

        outcome = await replay(transcript)

        assert RepairKind.NO_TOOL_CALL_FOUND.value in outcome.repairs
        assert "prometheus_query" in outcome.model.corrections[0]
        assert [
            {"name": call.name, "arguments": dict(call.arguments)}
            for call in outcome.final.tool_calls
        ] == expected_sequence(transcript)


class TestArgumentsAgainstTheSchema:
    async def test_an_out_of_schema_argument_is_rejected_by_name(self) -> None:
        transcript = load("out_of_schema_argument")

        outcome = await replay(transcript)

        assert RepairKind.UNKNOWN_ARGUMENT_REJECTED.value in outcome.repairs
        rejected = {
            repair.parameter
            for result in outcome.results
            for repair in result.repairs
            if repair.kind is RepairKind.UNKNOWN_ARGUMENT_REJECTED
        }
        assert rejected == set(transcript.expected["rejected_parameters"])

    async def test_the_capability_is_never_called_with_the_rejected_argument(self) -> None:
        transcript = load("out_of_schema_argument")

        outcome = await replay(transcript)

        for call in outcome.final.tool_calls:
            assert "label_selector" not in call.arguments

    async def test_a_missing_required_argument_produces_a_specific_correction(self) -> None:
        transcript = load("missing_required_argument")

        outcome = await replay(transcript)

        correction = outcome.model.corrections[0]
        assert "namespace" in correction
        assert "kubernetes_list_pods" in correction
        # Nothing was supplied for it, which is the half of this that matters.
        assert "checkout" not in correction

    async def test_the_repaired_call_carries_only_what_the_model_supplied(self) -> None:
        transcript = load("missing_required_argument")

        outcome = await replay(transcript)

        assert [
            {"name": call.name, "arguments": dict(call.arguments)}
            for call in outcome.final.tool_calls
        ] == expected_sequence(transcript)


class TestDoubledAndRepeatedCalls:
    async def test_the_second_copy_in_one_turn_is_dropped(self) -> None:
        transcript = load("two_calls_where_one_expected")

        outcome = await replay(transcript)

        assert RepairKind.DUPLICATE_CALL_DISCARDED.value in outcome.repairs
        assert [
            {"name": call.name, "arguments": dict(call.arguments)}
            for call in outcome.final.tool_calls
        ] == expected_sequence(transcript)

    async def test_two_different_calls_in_one_turn_are_both_kept(self) -> None:
        transcript = load("two_calls_where_one_expected")

        outcome = await replay(transcript, turns=2)

        assert len(outcome.results[1].tool_calls) == 2

    async def test_a_model_stuck_on_one_call_is_broken_out_of_inside_the_window(self) -> None:
        transcript = load("identical_repeated_calls")

        outcome = await replay(transcript, turns=len(transcript.outputs))

        broke_on = next(
            index
            for index, result in enumerate(outcome.results, start=1)
            if any(repair.kind is RepairKind.REPETITION_BROKEN for repair in result.repairs)
        )
        assert broke_on == transcript.expected["broken_at_output"]
        assert broke_on < MAX_IDENTICAL_CALLS_IN_WINDOW + 1

    async def test_the_model_is_told_what_it_is_repeating(self) -> None:
        transcript = load("identical_repeated_calls")

        outcome = await replay(transcript, turns=len(transcript.outputs))

        assert any("prometheus_query" in correction for correction in outcome.model.corrections)


class TestAStreamedCallInPieces:
    async def test_the_fragments_are_reassembled_into_one_call(self) -> None:
        transcript = load("fragmented_streamed_call")

        events = [event async for event in streamed_events(transcript)]

        calls = [event.tool_call for event in events if event.kind is StreamEventKind.TOOL_CALL]
        assert len(calls) == 1
        assert calls[0] is not None
        assert {"name": calls[0].name, "arguments": dict(calls[0].arguments)} == expected_sequence(
            transcript
        )[0]

    async def test_the_text_around_the_call_is_still_delivered(self) -> None:
        transcript = load("fragmented_streamed_call")

        events = [event async for event in streamed_events(transcript)]

        assert any(event.kind is StreamEventKind.TEXT_DELTA for event in events)


class TestAnOversizedCapabilityResult:
    #: What a model with an 8k-token measured window may be shown of one result.
    CEILING = ModelLimits(usable_context_tokens=8_000).tool_result_chars

    def test_what_the_model_reads_is_shortened_and_says_so(self) -> None:
        transcript = load("oversized_capability_result")

        shortened = truncate_for_model(
            transcript.capability_result, evidence_id="e1", ceiling=self.CEILING
        )

        assert shortened.truncated
        assert len(shortened.content) < len(transcript.capability_result)
        assert "e1" in shortened.content

    def test_the_whole_result_is_what_the_trace_keeps(self) -> None:
        transcript = load("oversized_capability_result")

        shortened = truncate_for_model(
            transcript.capability_result, evidence_id="e1", ceiling=self.CEILING
        )

        assert shortened.full == transcript.capability_result
        assert len(shortened.full) > self.CEILING

    def test_a_result_inside_the_bound_is_left_exactly_as_it_was(self) -> None:
        shortened = truncate_for_model(
            "two pods are unhealthy", evidence_id="e1", ceiling=self.CEILING
        )

        assert not shortened.truncated
        assert shortened.content == "two pods are unhealthy"

    def test_a_deployment_that_never_measured_its_model_shortens_nothing(self) -> None:
        transcript = load("oversized_capability_result")

        shortened = truncate_for_model(
            transcript.capability_result,
            evidence_id="e1",
            ceiling=ModelLimits().tool_result_chars,
        )

        assert not shortened.truncated
        assert shortened.content == transcript.capability_result


class TestAnEndpointThatAnswersTwoHundredWithAnError:
    def test_the_body_decides_the_classification_rather_than_the_status(self) -> None:
        transcript = load("success_with_error_body")
        error = transcript.error_body["document"]["error"]

        classification = classify(
            ErrorObservation(
                status_code=int(transcript.error_body["status_code"]),
                error_code=str(error["code"]),
                message=str(error["message"]),
            )
        )

        assert classification is FailureClass(transcript.expected["failure"])
        assert classification is not FailureClass.MODEL_BEHAVIOUR

    async def test_a_client_reads_the_body_rather_than_reporting_an_empty_turn(self) -> None:
        transcript = load("success_with_error_body")
        transport = RecordedTransport(responses=[transcript.error_body["document"]])
        client = build_client(PROVIDER_OLLAMA, transport=transport)

        result = await client.invoke(
            InvokeRequest(messages=(Message(role=Role.USER, text="Why is checkout failing?"),))
        )

        assert not result.succeeded
        assert result.failure is FailureClass(transcript.expected["failure"])
        # The distinction FR-021 turns on: the endpoint is at fault, not the
        # model, and an operator sent to change model would change nothing.
        assert result.failure is not FailureClass.MODEL_BEHAVIOUR


class TestTheRecordedSetIsWhollyDriven:
    def test_every_transcript_on_disk_is_exercised_by_this_file(self) -> None:
        assert set(transcript_ids()) == DRIVEN

    @pytest.mark.parametrize("transcript_id", transcript_ids())
    def test_every_transcript_says_what_it_stands_for(self, transcript_id: str) -> None:
        transcript = load(transcript_id)

        assert transcript.description.strip()
        assert transcript.expected

    def test_no_transcript_carries_anything_resembling_a_credential(self) -> None:
        for transcript_id in transcript_ids():
            raw = (
                load(transcript_id).description + str(load(transcript_id).error_body) + MODEL_ID
            ).lower()
            for marker in ("api_key", "secret", "bearer ", "password", "token="):
                assert marker not in raw
