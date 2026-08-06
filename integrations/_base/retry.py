"""When to try a vendor call again, and how long to wait first.

Retrying is where a well-meaning integration turns a vendor's bad ten seconds
into its own bad ten minutes. Three rules keep that from happening, and each one
is a decision somebody would otherwise make differently per vendor.

**Only retryable classes are retried.** Re-sending invalid arguments produces
the same invalid arguments; re-requesting a denied permission produces the same
denial. Both burn an iteration of a bounded loop to learn nothing, and the loop's
budget is the investigation's budget.

**``Retry-After`` wins.** When a vendor says how long to wait, waiting a
different amount is a decision to be rate-limited again. The header is honoured
up to the policy's ceiling — a vendor asking for an hour gets the ceiling and a
failure, because an investigation that sleeps for an hour has already failed.

**Jitter is proportional and always applied.** Several capabilities run in
parallel against the same vendor, and a fixed backoff schedules all of their
retries for the same instant, which is the thundering herd that caused the rate
limit in the first place.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from integrations._base.errors import IntegrationError, IntegrationErrorReason

#: Ceiling on an honoured ``Retry-After``. Past this the wait costs more than
#: the answer is worth, and failing tells the investigation to try something
#: else while it still has budget.
MAX_HONOURED_RETRY_AFTER_SECONDS = 30.0

#: The reasons worth repeating. Everything else is a state the vendor or the
#: operator has to change first.
RETRYABLE_REASONS: frozenset[IntegrationErrorReason] = frozenset(
    {
        IntegrationErrorReason.RATE_LIMITED,
        IntegrationErrorReason.TIMEOUT,
        IntegrationErrorReason.UPSTREAM_ERROR,
        IntegrationErrorReason.PROXY_UNAVAILABLE,
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How many attempts, how long between them, and which failures qualify.

    Declared per integration where a vendor genuinely differs, and left at the
    default everywhere else — which is most places, because the default is what
    the vendors' own documentation converges on.
    """

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("a retry policy must permit at least one attempt")
        if not 0.0 <= self.jitter_ratio <= 1.0:
            raise ValueError("jitter_ratio is a proportion of the delay, so it is in [0, 1]")

    def should_retry(self, error: IntegrationError, *, attempt: int) -> bool:
        """Return whether ``error`` on ``attempt`` is worth trying again.

        ``attempt`` counts from one, so the last attempt never schedules
        another — a policy of three attempts makes three calls, not four.
        """
        if attempt >= self.max_attempts:
            return False
        return error.reason in RETRYABLE_REASONS

    def delay_for(
        self,
        attempt: int,
        *,
        retry_after: float | None = None,
        jitter: float | None = None,
    ) -> float:
        """Return how long to wait before attempt ``attempt + 1``.

        ``jitter`` is injectable so a test can assert the schedule rather than
        assert a range. In production it is drawn per call, which is the whole
        point of it.
        """
        if retry_after is not None:
            return min(max(retry_after, 0.0), MAX_HONOURED_RETRY_AFTER_SECONDS)

        exponential = self.base_delay_seconds * (2 ** max(attempt - 1, 0))
        bounded = min(exponential, self.max_delay_seconds)
        drawn = jitter if jitter is not None else random.random()
        return float(bounded * (1.0 + self.jitter_ratio * (drawn * 2.0 - 1.0)))


def parse_retry_after(value: str | None) -> float | None:
    """Return the seconds a ``Retry-After`` header asks for, or ``None``.

    Only the delta-seconds form. The HTTP-date form exists and is rare, and
    parsing it wrong — which means parsing it in the wrong timezone — produces a
    wait of hours rather than seconds. Falling back to the policy's own backoff
    is the safer failure.
    """
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


__all__ = [
    "MAX_HONOURED_RETRY_AFTER_SECONDS",
    "RETRYABLE_REASONS",
    "RetryPolicy",
    "parse_retry_after",
]
