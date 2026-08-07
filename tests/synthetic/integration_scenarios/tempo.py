"""Tempo, end to end: capability, client, proxy, injection, vendor.

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
    "token": "ninjasre-scenario-token-000000",
}


TRACE_STATISTICS: Final = IntegrationScenario(
    key="tempo-trace-statistics",
    integration="tempo",
    capability="tempo_trace_statistics",
    arguments={
        "service": '{resource.service.name="checkout"}',
        "start": "1754499600",
        "end": "1754503200",
        "group_by": "rootServiceName",
    },
    responses=(
        json_response(
            {
                "traces": [
                    {"traceID": "a1", "rootServiceName": "checkout"},
                    {"traceID": "a2", "rootServiceName": "checkout"},
                    {"traceID": "a3", "rootServiceName": "payments"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 traces across",
    expected_paths=("/api/search",),
)


SLOW_TRACES: Final = IntegrationScenario(
    key="tempo-slow-traces",
    integration="tempo",
    capability="tempo_slow_traces",
    arguments={
        "service": "{duration > 1s}",
        "start": "1754499600",
        "end": "1754503200",
        "limit": 5,
    },
    responses=(
        json_response(
            {"traces": [{"traceID": "a1", "rootServiceName": "checkout", "durationMs": 1420}]}
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 traces from Tempo",
    expected_paths=("/api/search",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (TRACE_STATISTICS, SLOW_TRACES)

__all__ = ["CREDENTIAL", "SCENARIOS", "TRACE_STATISTICS", "SLOW_TRACES"]
