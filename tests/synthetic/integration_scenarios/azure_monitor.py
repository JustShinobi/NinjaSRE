"""Azure Monitor, end to end: capability, client, proxy, injection, vendor.

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
    "workspace": "00000000-0000-0000-0000-000000000000",
}


LOG_STATISTICS: Final = IntegrationScenario(
    key="azure_monitor-log-statistics",
    integration="azure_monitor",
    capability="azure_monitor_log_statistics",
    arguments={
        "query": "AppTraces | summarize count() by SeverityLevel",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "group_by": "name",
    },
    responses=(
        json_response(
            {
                "tables": [
                    {"name": "PrimaryResult", "rows": [["error", 412]]},
                    {"name": "PrimaryResult", "rows": [["info", 38104]]},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 log lines across",
    expected_paths=("/v1/workspaces/00000000-0000-0000-0000-000000000000/query",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="azure_monitor-sample-logs",
    integration="azure_monitor",
    capability="azure_monitor_sample_logs",
    arguments={
        "query": "AppTraces | take 20",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "limit": 5,
    },
    responses=(
        json_response(
            {"tables": [{"name": "PrimaryResult", "rows": [["cart serialiser out of memory"]]}]}
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 log lines from Azure Monitor",
    expected_paths=("/v1/workspaces/00000000-0000-0000-0000-000000000000/query",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]
