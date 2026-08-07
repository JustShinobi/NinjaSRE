"""Honeycomb, end to end: capability, client, proxy, injection, vendor.

The seventh parity artefact. Everything else about an integration can look
finished while nothing exercises the path a real call takes — and the first
thing to notice that is the investigation which needed it.

So these drive the whole path: the registered capability, the client, the real
credential proxy with this integration's own injection rule, and a scripted
vendor on the far side. Nothing is mocked between the tool and the wire, which
is what makes a renamed response field fail here rather than at 03:00.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

#: Not a real credential. The suite asserts that none of these values reaches a
#: client, a result, or a trace, which is the property SC-003 is about.
CREDENTIAL: Final[dict[str, str]] = {
    "api_key": "ninjasre-scenario-key-000000",
    "dataset": "checkout",
}


TRACE_STATISTICS: Final = IntegrationScenario(
    key="honeycomb-trace-statistics",
    integration="honeycomb",
    capability="honeycomb_trace_statistics",
    arguments={"service": "checkout", "start": "", "end": "", "group_by": "name"},
    responses=(
        json_response(
            [
                {"name": "GET /cart", "duration_ms": 1420},
                {"name": "GET /cart", "duration_ms": 980},
                {"name": "POST /pay", "duration_ms": 120},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 traces across",
    expected_paths=("/1/events/checkout",),
)


SLOW_TRACES: Final = IntegrationScenario(
    key="honeycomb-slow-traces",
    integration="honeycomb",
    capability="honeycomb_slow_traces",
    arguments={"service": "checkout", "start": "", "end": "", "limit": 5},
    responses=(
        json_response([{"name": "GET /cart", "duration_ms": 1420, "trace.trace_id": "abc123"}]),
    ),
    credential=CREDENTIAL,
    expected_summary="1 traces from Honeycomb",
    expected_paths=("/1/events/checkout",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (TRACE_STATISTICS, SLOW_TRACES)

__all__ = ["CREDENTIAL", "SCENARIOS", "TRACE_STATISTICS", "SLOW_TRACES"]
