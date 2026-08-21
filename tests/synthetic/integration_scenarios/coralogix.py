"""Coralogix, end to end: capability, client, proxy, injection, vendor.

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
    key="coralogix-log-statistics",
    integration="coralogix",
    capability="coralogix_log_statistics",
    arguments={
        "query": "source logs",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "group_by": "userData.severity",
    },
    responses=(
        json_response(
            {
                "result": {
                    "results": [
                        {"userData": {"severity": "ERROR", "message": "oom"}},
                        {"userData": {"severity": "ERROR", "message": "oom"}},
                        {"userData": {"severity": "INFO", "message": "ok"}},
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 log lines across",
    expected_paths=("/api/v1/dataprime/query",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="coralogix-sample-logs",
    integration="coralogix",
    capability="coralogix_sample_logs",
    arguments={
        "query": 'source logs | filter $l.severity == "ERROR"',
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "limit": 5,
    },
    responses=(
        json_response(
            {"result": {"results": [{"userData": {"severity": "ERROR", "message": "oom"}}]}}
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 log lines from Coralogix",
    expected_paths=("/api/v1/dataprime/query",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]
