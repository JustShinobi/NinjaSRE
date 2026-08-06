"""The proxy hop's own cost, held to a budget (the latency risk in the plan).

Making the proxy mandatory means every authenticated call pays for it, so "does
the proxy add unacceptable latency" is the first question anybody asks. The
answer has to be a measurement rather than an assurance, and it has to keep
being true — which is what a budgeted benchmark is for.

**What is measured.** Resolution, the allow-list check, injection, the audit
write, and the in-process mount, with the vendor call replaced by a sender that
returns immediately. That is exactly the work the proxy adds; a real vendor call
dominates it by two to three orders of magnitude.

**Why p50 and not the mean.** A garbage collection pause during the run moves a
mean and not a median, and a benchmark that fails on somebody's laptop for a
reason unrelated to the code is a benchmark people learn to re-run rather than
read.

**Why this is not in ``make verify``'s critical path.** It is, and deliberately:
it takes well under a second. A performance gate that runs nightly is a
performance gate whose regressions are found by whoever happens to look.
"""

from __future__ import annotations

import statistics
import time

import pytest

from config.constants.security import CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS
from integrations._base.transport import InProcessProxyTransport
from tests.unit.platform.credentials.conftest import Harness, build_harness, json_response
from tests.unit.platform.credentials.test_proxy_engine import FIRST_KEY, request

pytestmark = [pytest.mark.benchmark, pytest.mark.unit]

#: Enough samples for a stable median, few enough that the suite stays fast.
SAMPLES = 200

#: Discarded before measuring. The first call imports, compiles, and warms the
#: fake datastore's dictionaries, and including it would measure Python's
#: startup rather than the proxy's work.
WARMUP = 20


async def _seeded() -> Harness:
    """Return a harness with one credential and an endless supply of responses."""
    harness = await build_harness()
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    return harness


async def _measure(call, samples: int = SAMPLES) -> list[float]:
    """Return the per-call durations of ``call``, warm-up excluded."""
    for _ in range(WARMUP):
        await call()
    timings: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        await call()
        timings.append(time.perf_counter() - started)
    return timings


async def test_the_engine_stays_inside_the_p50_budget() -> None:
    """The whole sequence: rate limit, rule, allow-list, resolve, inject, audit."""
    harness = await _seeded()

    async def one() -> None:
        harness.sender.responses.append(json_response({}))
        await harness.engine.forward(request())

    timings = await _measure(one)
    p50 = statistics.median(timings)

    assert p50 < CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS, (
        f"the proxy hop's p50 is {p50 * 1000:.3f}ms, above the "
        f"{CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS * 1000:.1f}ms budget"
    )


async def test_the_in_process_mount_stays_inside_the_p50_budget() -> None:
    """The ``dev`` profile's whole path, envelope encoding included.

    Measured separately from the engine because the envelope is what a
    contributor's every local call pays for, and the argument that a mandatory
    proxy costs a developer nothing rests on this number rather than on the one
    above.
    """
    harness = await _seeded()
    transport = InProcessProxyTransport(harness.app)

    async def one() -> None:
        harness.sender.responses.append(json_response({}))
        await transport.forward(request())

    timings = await _measure(one)
    p50 = statistics.median(timings)

    assert p50 < CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS, (
        f"the in-process mount's p50 is {p50 * 1000:.3f}ms, above the "
        f"{CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS * 1000:.1f}ms budget"
    )


async def test_the_tail_is_not_pathological() -> None:
    """A p50 inside budget and a p99 in milliseconds would still be a problem.

    Bounded at ten times the budget rather than at the budget itself: the tail
    of any timed loop in a garbage-collected runtime includes a collection, and
    asserting otherwise measures the collector.
    """
    harness = await _seeded()

    async def one() -> None:
        harness.sender.responses.append(json_response({}))
        await harness.engine.forward(request())

    timings = sorted(await _measure(one))
    p99 = timings[int(len(timings) * 0.99) - 1]

    assert p99 < CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS * 10
