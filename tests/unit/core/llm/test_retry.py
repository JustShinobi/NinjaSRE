"""The retry decision, which is the classification decision.

Every class gets an explicit expectation here rather than a rule of thumb,
because "retry the ones that look temporary" is how a schema rejection ends up
being sent three times.
"""

from __future__ import annotations

import pytest

from config.constants.llm import LLM_RETRY_MAX_DELAY_SECONDS
from core.llm.failures import FailureClass
from core.llm.retry import RetryPolicy

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("classification", "retryable"),
    [
        (FailureClass.TRANSIENT, True),
        (FailureClass.RATE_LIMITED, True),
        (FailureClass.AUTH, False),
        (FailureClass.SCHEMA_REJECTED, False),
        (FailureClass.CONTEXT_EXCEEDED, False),
        (FailureClass.CONTENT_FILTERED, False),
        (FailureClass.MODEL_UNAVAILABLE, False),
        (FailureClass.UNKNOWN, False),
    ],
)
def test_each_class_has_one_retry_decision(classification: FailureClass, retryable: bool) -> None:
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(classification, attempt=1) is retryable


def test_the_attempt_ceiling_stops_even_a_retryable_class() -> None:
    policy = RetryPolicy(max_attempts=3)

    assert policy.should_retry(FailureClass.TRANSIENT, attempt=2) is True
    assert policy.should_retry(FailureClass.TRANSIENT, attempt=3) is False


def test_backoff_doubles() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=100.0)
    no_jitter = 0.0

    delays = [policy.delay_for(attempt, jitter=lambda: no_jitter) for attempt in (1, 2, 3, 4)]

    assert delays == [1.0, 2.0, 4.0, 8.0]


def test_jitter_only_ever_adds_and_only_within_its_ratio() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=100.0, jitter_ratio=0.25)

    floor = policy.delay_for(1, jitter=lambda: 0.0)
    ceiling = policy.delay_for(1, jitter=lambda: 0.999)

    assert floor == pytest.approx(1.0)
    assert 1.0 < ceiling <= 1.25


def test_the_delay_is_capped() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=5.0)

    assert policy.delay_for(20, jitter=lambda: 0.999) == pytest.approx(5.0)


def test_a_retry_after_header_wins_over_the_computed_backoff() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=60.0)

    assert policy.delay_for(1, retry_after_seconds=12.0, jitter=lambda: 0.5) == pytest.approx(12.0)


def test_a_retry_after_header_is_still_capped() -> None:
    """An hour-long header would outlive the usefulness of the answer."""
    policy = RetryPolicy()

    delay = policy.delay_for(1, retry_after_seconds=3_600.0, jitter=lambda: 0.0)

    assert delay == pytest.approx(LLM_RETRY_MAX_DELAY_SECONDS)


def test_a_nonsensical_retry_after_falls_back_to_the_backoff() -> None:
    policy = RetryPolicy(base_delay_seconds=2.0)

    assert policy.delay_for(1, retry_after_seconds=-5.0, jitter=lambda: 0.0) == pytest.approx(2.0)
