"""A capability failure is a value the loop can reason about, never an exception.

An unhandled exception from a tool ends the turn and takes the trace with it.
A classified failure is something the model can read, react to, and route
around — which is the difference between an investigation that degrades and one
that stops.
"""

from __future__ import annotations

import pytest

from core.capability.metadata import EvidenceType
from core.capability.result import (
    CapabilityError,
    CapabilityErrorClass,
    CapabilityResult,
    Evidence,
)

pytestmark = pytest.mark.unit


def test_a_successful_result_carries_its_value() -> None:
    result = CapabilityResult.ok("datadog_log_statistics", value={"count": 412})

    assert result.succeeded
    assert result.error is None
    assert result.value == {"count": 412}


def test_a_failed_result_carries_a_classification_rather_than_raising() -> None:
    result = CapabilityResult.failed(
        "datadog_log_statistics",
        CapabilityErrorClass.UPSTREAM_ERROR,
        "Datadog returned 503.",
    )

    assert not result.succeeded
    assert result.value is None
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.UPSTREAM_ERROR


def test_the_error_taxonomy_is_closed() -> None:
    assert {member.value for member in CapabilityErrorClass} == {
        "invalid_arguments",
        "unavailable",
        "upstream_error",
        "timeout",
        "rate_limited",
        "permission_denied",
        "approval_required",
        "not_found",
        "internal",
    }


@pytest.mark.parametrize(
    ("classification", "retryable"),
    [
        (CapabilityErrorClass.TIMEOUT, True),
        (CapabilityErrorClass.RATE_LIMITED, True),
        (CapabilityErrorClass.UPSTREAM_ERROR, True),
        (CapabilityErrorClass.INVALID_ARGUMENTS, False),
        (CapabilityErrorClass.PERMISSION_DENIED, False),
        (CapabilityErrorClass.APPROVAL_REQUIRED, False),
        (CapabilityErrorClass.NOT_FOUND, False),
        (CapabilityErrorClass.UNAVAILABLE, False),
        (CapabilityErrorClass.INTERNAL, False),
    ],
)
def test_retryability_is_a_property_of_the_class(
    classification: CapabilityErrorClass, retryable: bool
) -> None:
    """Retrying an invalid argument list produces the same invalid argument list."""
    assert classification.retryable is retryable


def test_a_result_carries_the_evidence_it_produced() -> None:
    evidence = Evidence(
        source="datadog",
        evidence_type=EvidenceType.LOG,
        summary="412 errors on checkout-api in the last 15 minutes.",
        reference="datadog:logs:query-8821",
    )
    result = CapabilityResult.ok("datadog_log_statistics", value={}, evidence=[evidence])

    assert result.evidence == (evidence,)


def test_a_failed_result_may_still_carry_partial_evidence() -> None:
    """A tool that timed out after two of three regions still learned something."""
    evidence = Evidence(source="datadog", evidence_type=EvidenceType.LOG, summary="eu-west: 0")
    result = CapabilityResult.failed(
        "datadog_log_statistics",
        CapabilityErrorClass.TIMEOUT,
        "us-east did not respond within the budget.",
        evidence=[evidence],
    )

    assert not result.succeeded
    assert result.evidence == (evidence,)


def test_an_error_message_is_required() -> None:
    with pytest.raises(ValueError, match="message"):
        CapabilityError(classification=CapabilityErrorClass.INTERNAL, message="")


def test_results_are_immutable() -> None:
    result = CapabilityResult.ok("t", value=1)
    with pytest.raises(AttributeError):
        result.value = 2  # type: ignore[misc]
