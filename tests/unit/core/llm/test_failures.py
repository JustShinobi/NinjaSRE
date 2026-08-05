"""Every provider failure lands in exactly one class, and the class decides retry.

The taxonomy is closed on purpose. An unrecognised failure is ``UNKNOWN`` and is
not retried, because repeating a request nobody understands is how a rate limit
becomes an outage.
"""

from __future__ import annotations

import pytest

from core.llm.failures import (
    RETRYABLE_CLASSES,
    ErrorObservation,
    FailureClass,
    ProviderFailure,
    classify,
)

pytestmark = pytest.mark.unit


def test_taxonomy_is_closed() -> None:
    assert {member.value for member in FailureClass} == {
        "transient",
        "rate_limited",
        "auth",
        "schema_rejected",
        "context_exceeded",
        "content_filtered",
        "model_unavailable",
        "unknown",
    }


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, FailureClass.AUTH),
        (403, FailureClass.AUTH),
        (404, FailureClass.MODEL_UNAVAILABLE),
        (408, FailureClass.TRANSIENT),
        (409, FailureClass.TRANSIENT),
        (429, FailureClass.RATE_LIMITED),
        (500, FailureClass.TRANSIENT),
        (502, FailureClass.TRANSIENT),
        (503, FailureClass.TRANSIENT),
        (504, FailureClass.TRANSIENT),
        (529, FailureClass.TRANSIENT),
    ],
)
def test_status_codes_classify_without_a_body(status_code: int, expected: FailureClass) -> None:
    assert classify(ErrorObservation(status_code=status_code)) is expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("prompt is too long: 250000 tokens > 200000 maximum", FailureClass.CONTEXT_EXCEEDED),
        ("This model's maximum context length is 128000 tokens", FailureClass.CONTEXT_EXCEEDED),
        ("tools.0.custom.input_schema: unknown field 'oneOf'", FailureClass.SCHEMA_REJECTED),
        ("Invalid schema for function 'grafana_query'", FailureClass.SCHEMA_REJECTED),
        (
            "The response was filtered by the content management policy",
            FailureClass.CONTENT_FILTERED,
        ),
        ("something nobody has seen before", FailureClass.UNKNOWN),
    ],
)
def test_a_400_is_decided_by_what_the_provider_said(message: str, expected: FailureClass) -> None:
    assert classify(ErrorObservation(status_code=400, message=message)) is expected


@pytest.mark.parametrize(
    ("error_code", "expected"),
    [
        ("rate_limit_error", FailureClass.RATE_LIMITED),
        ("insufficient_quota", FailureClass.RATE_LIMITED),
        ("authentication_error", FailureClass.AUTH),
        ("permission_error", FailureClass.AUTH),
        ("overloaded_error", FailureClass.TRANSIENT),
        ("context_length_exceeded", FailureClass.CONTEXT_EXCEEDED),
        ("content_filter", FailureClass.CONTENT_FILTERED),
        ("model_not_found", FailureClass.MODEL_UNAVAILABLE),
    ],
)
def test_a_provider_error_code_outranks_a_bare_status(
    error_code: str, expected: FailureClass
) -> None:
    observation = ErrorObservation(status_code=400, error_code=error_code)
    assert classify(observation) is expected


@pytest.mark.parametrize(
    "exception_type",
    ["APITimeoutError", "ConnectTimeout", "APIConnectionError", "ReadTimeout"],
)
def test_a_transport_exception_with_no_response_is_transient(exception_type: str) -> None:
    assert classify(ErrorObservation(exception_type=exception_type)) is FailureClass.TRANSIENT


def test_nothing_at_all_is_unknown() -> None:
    assert classify(ErrorObservation()) is FailureClass.UNKNOWN


def test_only_transient_and_rate_limited_are_retryable() -> None:
    assert frozenset({FailureClass.TRANSIENT, FailureClass.RATE_LIMITED}) == RETRYABLE_CLASSES


def test_provider_failure_carries_its_classification_and_provider() -> None:
    failure = ProviderFailure(
        FailureClass.RATE_LIMITED,
        provider_id="anthropic",
        message="slow down",
        status_code=429,
        retry_after_seconds=7.5,
    )

    assert failure.classification is FailureClass.RATE_LIMITED
    assert failure.provider_id == "anthropic"
    assert failure.status_code == 429
    assert failure.retry_after_seconds == pytest.approx(7.5)
    assert failure.is_retryable is True


def test_a_non_transient_failure_reports_itself_as_not_retryable() -> None:
    failure = ProviderFailure(FailureClass.AUTH, provider_id="openai", message="bad key")
    assert failure.is_retryable is False
