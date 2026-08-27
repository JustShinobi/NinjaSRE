"""What a run's own evidence assessment says, read back off its recorded calls."""

from __future__ import annotations

from platform.persistence.ports.run_trace_store import ToolCallRecord, ToolCallStatus
from platform.runs.evidence import EvidenceAssessment, assessment_from_calls


def _call(
    name: str,
    *,
    call_id: str = "call-1",
    arguments: dict[str, object] | None = None,
    status: ToolCallStatus = ToolCallStatus.SUCCEEDED,
) -> ToolCallRecord:
    return ToolCallRecord(
        call_id=call_id,
        run_id="run-1",
        turn_id="turn-1",
        tool_name=name,
        status=status,
        arguments=arguments or {},
    )


def test_a_run_that_never_assessed_its_evidence_says_so_rather_than_scoring_nought() -> None:
    """No assessment is not the same fact as an assessment that found nothing."""
    assessment = assessment_from_calls(
        (_call("proxmox_guest_tasks"), _call("query_service_topology", call_id="call-2"))
    )

    assert assessment == EvidenceAssessment()
    assert assessment.assessed is False
    assert assessment.backed == 0
    assert assessment.missing == 0


def test_the_assessment_counts_what_the_run_said_it_could_and_could_not_back() -> None:
    """The recorder nests a call's own arguments beside its result, so this
    reads the shape `RunRecorder.record_call` actually writes rather than the
    flat one the capability's signature suggests."""
    assessment = assessment_from_calls(
        (
            _call("proxmox_quorum_status"),
            _call(
                "assess_evidence_sufficiency",
                call_id="call-2",
                arguments={
                    "arguments": {
                        "conclusion": "the container was stopped by hand",
                        "supporting_evidence": ["quorum", "topology", "guest tasks"],
                        "missing_evidence": [],
                    },
                    "result": {"sufficient": True},
                    "duration_ms": 1,
                },
            ),
        )
    )

    assert assessment.assessed is True
    assert assessment.backed == 3
    assert assessment.missing == 0
    assert assessment.claims == 3
    assert assessment.sufficient is True


def test_evidence_the_run_could_not_get_is_counted_and_the_assessment_is_not_sufficient() -> None:
    assessment = assessment_from_calls(
        (
            _call(
                "assess_evidence_sufficiency",
                arguments={
                    "arguments": {
                        "supporting_evidence": ["guest tasks", "topology"],
                        "missing_evidence": ["container logs"],
                    }
                },
            ),
        )
    )

    assert assessment.backed == 2
    assert assessment.missing == 1
    assert assessment.claims == 3
    assert assessment.sufficient is False


def test_the_last_assessment_wins_because_a_run_may_reconsider() -> None:
    """A loop that assessed twice concluded once, and it concluded last."""
    assessment = assessment_from_calls(
        (
            _call(
                "assess_evidence_sufficiency",
                call_id="call-1",
                arguments={
                    "arguments": {
                        "supporting_evidence": ["one"],
                        "missing_evidence": ["logs", "metrics"],
                    }
                },
            ),
            _call(
                "assess_evidence_sufficiency",
                call_id="call-2",
                arguments={
                    "arguments": {
                        "supporting_evidence": ["one", "two", "three"],
                        "missing_evidence": [],
                    }
                },
            ),
        )
    )

    assert assessment.backed == 3
    assert assessment.missing == 0


def test_a_failed_assessment_call_is_not_read_as_an_answer() -> None:
    """A capability that raised said nothing, whatever arguments it was given."""
    assessment = assessment_from_calls(
        (
            _call(
                "assess_evidence_sufficiency",
                arguments={"arguments": {"supporting_evidence": ["one"], "missing_evidence": []}},
                status=ToolCallStatus.FAILED,
            ),
        )
    )

    assert assessment.assessed is False


def test_an_argument_that_is_not_a_list_is_counted_as_nothing_rather_than_as_one() -> None:
    """The model writes these arguments, so the reader never trusts their shape."""
    assessment = assessment_from_calls(
        (
            _call(
                "assess_evidence_sufficiency",
                arguments={
                    "arguments": {"supporting_evidence": "three things", "missing_evidence": None}
                },
            ),
        )
    )

    assert assessment.assessed is True
    assert assessment.backed == 0
    assert assessment.missing == 0


def test_the_flat_shape_is_still_read_for_a_caller_that_records_one() -> None:
    """Not every recorder wraps. A reader that only understood the wrapper
    would silently score a flat record as an assessment that named nothing."""
    assessment = assessment_from_calls(
        (
            _call(
                "assess_evidence_sufficiency",
                arguments={"supporting_evidence": ["one", "two"], "missing_evidence": []},
            ),
        )
    )

    assert assessment.backed == 2


def test_the_result_answers_when_the_arguments_were_truncated_away() -> None:
    """An oversized payload is truncated before it is stored, and the two
    halves are not truncated together. Whichever survives is read."""
    assessment = assessment_from_calls(
        (
            _call(
                "assess_evidence_sufficiency",
                arguments={
                    "arguments": {},
                    "result": {
                        "supporting_evidence": ["one", "two"],
                        "missing_evidence": ["logs"],
                    },
                },
            ),
        )
    )

    assert assessment.backed == 2
    assert assessment.missing == 1


def test_an_assessment_that_named_nothing_at_all_is_not_a_sufficient_one() -> None:
    """This is what staging drew as a green "0 of 0 claims backed": a run that
    called the capability with nothing in either list said nothing, and
    nothing is not the same as having found nothing outstanding."""
    assessment = assessment_from_calls(
        (
            _call(
                "assess_evidence_sufficiency",
                arguments={"arguments": {"supporting_evidence": [], "missing_evidence": []}},
            ),
        )
    )

    assert assessment.assessed is True
    assert assessment.claims == 0
    assert assessment.sufficient is False


def test_the_assessment_carries_the_evidence_it_named_not_only_how_much() -> None:
    """A count is enough for a list of runs. A reader who opened one wants the
    sentences, and the trace already holds them."""
    assessment = assessment_from_calls(
        (
            _call(
                "assess_evidence_sufficiency",
                arguments={
                    "arguments": {
                        "supporting_evidence": ["the guest task log names a person", 7],
                        "missing_evidence": ["the container logs"],
                    }
                },
            ),
        )
    )

    assert assessment.supporting == ("the guest task log names a person",)
    assert assessment.missing_evidence == ("the container logs",)
    # The count and the names never disagree: both drop the entry that was
    # not a string, rather than one counting it and the other not.
    assert assessment.backed == 1
