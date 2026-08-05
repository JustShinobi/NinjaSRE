"""When to try again, decided by what went wrong.

Retry lives next to classification because they are one decision, not two. A
generic decorator would have to be told at every call site which errors are
worth repeating, and the answer depends on the provider's response shape — which
is knowledge ``core.llm.failures`` owns. Keeping them together means the rule is
in one place and auditable; splitting them means it is in every place.

The jitter source is injected rather than read from a module-level random
generator. A backoff test that cannot pin the delay is a test that either sleeps
for real or asserts nothing.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from config.constants.llm import (
    LLM_MAX_RETRIES,
    LLM_RETRY_BASE_DELAY_SECONDS,
    LLM_RETRY_JITTER_RATIO,
    LLM_RETRY_MAX_DELAY_SECONDS,
)
from core.llm.failures import RETRYABLE_CLASSES, FailureClass

#: Returns a fraction in ``[0, 1)`` used to spread retries apart.
JitterSource = Callable[[], float]


def _default_jitter() -> float:
    """Return a uniform fraction in ``[0, 1)``."""
    return random.random()  # noqa: S311 — spreading load, not choosing a secret


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential backoff with jitter, bounded by a fixed attempt ceiling."""

    max_attempts: int = LLM_MAX_RETRIES
    base_delay_seconds: float = LLM_RETRY_BASE_DELAY_SECONDS
    max_delay_seconds: float = LLM_RETRY_MAX_DELAY_SECONDS
    jitter_ratio: float = LLM_RETRY_JITTER_RATIO

    def should_retry(self, classification: FailureClass, attempt: int) -> bool:
        """Return whether attempt ``attempt`` (1-based) should be followed by another.

        Only ``transient`` and ``rate_limited`` qualify. A rejected schema will
        be rejected again, a bad key will still be bad, and repeating either
        spends the operator's quota to learn nothing.
        """
        if attempt >= self.max_attempts:
            return False
        return classification in RETRYABLE_CLASSES

    def delay_for(
        self,
        attempt: int,
        *,
        retry_after_seconds: float | None = None,
        jitter: JitterSource | None = None,
    ) -> float:
        """Return how long to wait before attempt ``attempt + 1``.

        A ``Retry-After`` the provider sent wins over the computed backoff, and
        is still capped: a header asking for an hour would stall an
        investigation past the point where its answer is useful.
        """
        source = jitter or _default_jitter

        if retry_after_seconds is not None and retry_after_seconds > 0:
            return min(retry_after_seconds, self.max_delay_seconds)

        # 2.0 rather than 2: an int base leaves the exponentiation's type open,
        # because a negative exponent would make it a float.
        exponential = self.base_delay_seconds * (2.0 ** max(attempt - 1, 0))
        capped = min(exponential, self.max_delay_seconds)
        spread = capped * self.jitter_ratio * source()
        return min(capped + spread, self.max_delay_seconds)


DEFAULT_RETRY_POLICY = RetryPolicy()


__all__ = ["DEFAULT_RETRY_POLICY", "JitterSource", "RetryPolicy"]
