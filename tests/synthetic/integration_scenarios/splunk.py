"""Splunk, end to end: capability, client, proxy, injection, vendor.

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
    key="splunk-log-statistics",
    integration="splunk",
    capability="splunk_log_statistics",
    arguments={
        "query": "search index=app checkout",
        "start": "-1h",
        "end": "now",
        "group_by": "log_level",
    },
    responses=(
        json_response(
            {
                "results": [
                    {"log_level": "ERROR", "_raw": "oom"},
                    {"log_level": "ERROR", "_raw": "oom"},
                    {"log_level": "INFO", "_raw": "ok"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 log lines across",
    expected_paths=("/services/search/jobs/export",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="splunk-sample-logs",
    integration="splunk",
    capability="splunk_sample_logs",
    arguments={
        "query": "search index=app checkout ERROR",
        "start": "-1h",
        "end": "now",
        "limit": 5,
    },
    responses=(json_response({"results": [{"log_level": "ERROR", "_raw": "oom"}]}),),
    credential=CREDENTIAL,
    expected_summary="1 log lines from Splunk",
    expected_paths=("/services/search/jobs/export",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]
