"""SigNoz, end to end: capability, client, proxy, injection, vendor.

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
}


TRACE_STATISTICS: Final = IntegrationScenario(
    key="signoz-trace-statistics",
    integration="signoz",
    capability="signoz_trace_statistics",
    arguments={
        "service": "checkout",
        "start": "1754499600000",
        "end": "1754503200000",
        "group_by": "name",
    },
    responses=(
        json_response(
            {
                "data": {
                    "result": [
                        {"name": "GET /cart", "durationNano": 1420000000},
                        {"name": "GET /cart", "durationNano": 980000000},
                        {"name": "POST /pay", "durationNano": 12000000},
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 traces across",
    expected_paths=("/api/v3/query_range",),
)


SLOW_TRACES: Final = IntegrationScenario(
    key="signoz-slow-traces",
    integration="signoz",
    capability="signoz_slow_traces",
    arguments={"service": "checkout", "start": "1754499600000", "end": "1754503200000", "limit": 5},
    responses=(
        json_response(
            {
                "data": {
                    "result": [
                        {"name": "GET /cart", "durationNano": 1420000000, "traceID": "abc123"}
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 traces from SigNoz",
    expected_paths=("/api/v3/query_range",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (TRACE_STATISTICS, SLOW_TRACES)

__all__ = ["CREDENTIAL", "SCENARIOS", "TRACE_STATISTICS", "SLOW_TRACES"]
