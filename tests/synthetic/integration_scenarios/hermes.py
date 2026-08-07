"""Hermes, end to end: capability, client, proxy, injection, vendor.

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


LOG_STATISTICS: Final = IntegrationScenario(
    key="hermes-log-statistics",
    integration="hermes",
    capability="hermes_log_statistics",
    arguments={
        "query": "checkout",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "group_by": "classification",
    },
    responses=(
        json_response(
            {
                "entries": [
                    {"classification": "resource-exhaustion", "message": "oom"},
                    {"classification": "resource-exhaustion", "message": "oom"},
                    {"classification": "informational", "message": "ok"},
                ],
                "next_cursor": None,
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 log lines across",
    expected_paths=("/v1/logs/search",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="hermes-sample-logs",
    integration="hermes",
    capability="hermes_sample_logs",
    arguments={
        "query": "checkout oom",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "limit": 5,
    },
    responses=(
        json_response(
            {
                "entries": [
                    {
                        "classification": "resource-exhaustion",
                        "message": "cart serialiser out of memory",
                    }
                ],
                "next_cursor": None,
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 log lines from Hermes",
    expected_paths=("/v1/logs/search",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]
