"""Loki, end to end: capability, client, proxy, injection, vendor.

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


LOG_STATISTICS: Final = IntegrationScenario(
    key="loki-log-statistics",
    integration="loki",
    capability="loki_log_statistics",
    arguments={
        "query": '{app="checkout"}',
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "group_by": "stream.level",
    },
    responses=(
        json_response(
            {
                "data": {
                    "result": [
                        {
                            "stream": {"level": "error", "app": "checkout"},
                            "values": [["1754503600000000000", "cart serialiser out of memory"]],
                        },
                        {"stream": {"level": "info", "app": "checkout"}, "values": []},
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 log lines across",
    expected_paths=("/loki/api/v1/query_range",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="loki-sample-logs",
    integration="loki",
    capability="loki_sample_logs",
    arguments={
        "query": '{app="checkout"} |= "error"',
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "limit": 5,
    },
    responses=(
        json_response(
            {
                "data": {
                    "result": [
                        {
                            "stream": {"level": "error"},
                            "values": [["1754503600000000000", "cart serialiser out of memory"]],
                        }
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 log lines from Loki",
    expected_paths=("/loki/api/v1/query_range",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]
