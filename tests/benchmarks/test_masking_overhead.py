"""What masking and scanning cost on an evidence payload of real size.

Ten megabytes is not a hypothetical. A pod's log window, a metrics range query,
and a `describe` across a namespace comfortably reach it between them, and a
control that is fine on a paragraph and quadratic on a payload is a control that
works in every test and fails during the one incident big enough to matter.

The budget is per megabyte rather than absolute, so it says something about the
algorithm rather than about the machine, and a payload of a different size can
be measured against the same number. It is set well above what the current
implementation spends: a failure here means a detector or a rule has started
backtracking, not that CI was busy.

The corpus is generated rather than fixed because the interesting cost is
scanning text that *nearly* matches — a log line full of pod-shaped names and
key-shaped strings is far more expensive than one full of prose, and a
benchmark over prose would measure nothing.
"""

from __future__ import annotations

import time

import pytest

from config.constants.security import MASKING_BUDGET_SECONDS_PER_MEGABYTE
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import default_ruleset
from platform.masking.context import MaskingContext
from platform.masking.policy import MaskingLevel, MaskingPolicy

pytestmark = [pytest.mark.benchmark]

MEGABYTE = 1024 * 1024
PAYLOAD_MEGABYTES = 10


def evidence_payload(megabytes: int) -> str:
    """Return a payload of roughly ``megabytes``, dense with near-matches.

    Every line carries something each detector and several rules have to look
    at and mostly reject, which is the expensive case rather than the
    convenient one.
    """
    block = "\n".join(
        (
            'container_memory_working_set_bytes{namespace="payments-prod",'
            'pod="checkout-7d9f8b6c5d-x2n4p"} 2147483648',
            "2026-08-06T12:34:56.789Z ERROR checkout-api OOMKilled restarts=4 node=10.42.17.203",
            "upstream db-primary.payments.svc.cluster.local:5432 refused connection",
            "assumed arn:aws:iam::417290583641:role/checkout-task in account 417290583641",
            "traceback: core.llm.client.invoke -> platform.guardrails.engine.scan",
            "authorization header present, bearer omitted from this line deliberately",
            "cluster=prod-eu-west-1-blue deployment=checkout-api service=checkout",
            "restart-policy-always backoff=30s reason=CrashLoopBackOff exit=137",
        )
    )
    repeats = (megabytes * MEGABYTE) // len(block) + 1
    return "\n".join([block] * repeats)


PAYLOAD = evidence_payload(PAYLOAD_MEGABYTES)
ACTUAL_MEGABYTES = len(PAYLOAD) / MEGABYTE


def test_masking_stays_within_its_budget_on_a_ten_megabyte_payload() -> None:
    """The masking half, on the payload size the budget was set for."""
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD))

    started = time.perf_counter()
    context.mask(PAYLOAD)
    elapsed = time.perf_counter() - started

    per_megabyte = elapsed / ACTUAL_MEGABYTES
    assert per_megabyte < MASKING_BUDGET_SECONDS_PER_MEGABYTE, (
        f"masking spent {per_megabyte:.3f}s per MB against a budget of "
        f"{MASKING_BUDGET_SECONDS_PER_MEGABYTE}s ({elapsed:.2f}s total)"
    )


def test_strict_masking_stays_within_the_same_budget() -> None:
    """The level with the most detectors turned on is the one worth timing."""
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STRICT))

    started = time.perf_counter()
    context.mask(PAYLOAD)
    elapsed = time.perf_counter() - started

    per_megabyte = elapsed / ACTUAL_MEGABYTES
    assert per_megabyte < MASKING_BUDGET_SECONDS_PER_MEGABYTE, (
        f"strict masking spent {per_megabyte:.3f}s per MB ({elapsed:.2f}s total)"
    )


def test_the_shipped_ruleset_stays_within_the_same_budget() -> None:
    """The guardrail half, over the same payload.

    The keyword prefilter is what makes this affordable: most rules never run
    their patterns, because the word that would justify running them is not in
    the text.
    """
    engine = GuardrailEngine(ruleset=default_ruleset())

    started = time.perf_counter()
    engine.scan(PAYLOAD)
    elapsed = time.perf_counter() - started

    per_megabyte = elapsed / ACTUAL_MEGABYTES
    assert per_megabyte < MASKING_BUDGET_SECONDS_PER_MEGABYTE, (
        f"the ruleset spent {per_megabyte:.3f}s per MB ({elapsed:.2f}s total)"
    )


def test_masking_cost_is_linear_in_payload_size() -> None:
    """A control that is fine at 1MB and quadratic at 10MB passes every other test.

    Comparing the per-megabyte rate at two sizes is what catches that, and it is
    a stronger claim than any single absolute number.
    """
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD))
    small = evidence_payload(1)

    started = time.perf_counter()
    context.mask(small)
    small_rate = (time.perf_counter() - started) / (len(small) / MEGABYTE)

    started = time.perf_counter()
    MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD)).mask(PAYLOAD)
    large_rate = (time.perf_counter() - started) / ACTUAL_MEGABYTES

    assert large_rate < small_rate * 4, (
        f"per-megabyte cost grew from {small_rate:.3f}s to {large_rate:.3f}s between "
        f"1MB and {ACTUAL_MEGABYTES:.0f}MB, which is not linear"
    )
