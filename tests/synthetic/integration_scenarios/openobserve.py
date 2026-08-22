"""OpenObserve, end to end: capability, client, proxy, injection, vendor.

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
    # What an operator submits on one screen. The address is not a credential
    # and is not stored with one — ``vault_values`` in the contract conftest is
    # what splits this the way the write route does.
    "endpoint": "https://openobserve.example.com",
    "username": "ninjasre-scenario",
    "password": "ninjasre-scenario-secret",
    "organisation": "default",
}


LOG_STATISTICS: Final = IntegrationScenario(
    key="openobserve-log-statistics",
    integration="openobserve",
    capability="openobserve_log_statistics",
    arguments={
        "query": "SELECT * FROM logs",
        "start": "1754499600000000",
        "end": "1754503200000000",
        "group_by": "level",
    },
    responses=(
        json_response(
            {
                "hits": [
                    {"level": "error", "message": "oom"},
                    {"level": "error", "message": "oom"},
                    {"level": "info", "message": "ok"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 log lines across",
    expected_paths=("/api/default/_search",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="openobserve-sample-logs",
    integration="openobserve",
    capability="openobserve_sample_logs",
    arguments={
        "query": "SELECT * FROM logs WHERE level = 'error'",
        "start": "1754499600000000",
        "end": "1754503200000000",
        "limit": 5,
    },
    responses=(json_response({"hits": [{"level": "error", "message": "oom"}]}),),
    credential=CREDENTIAL,
    expected_summary="1 log lines from OpenObserve",
    expected_paths=("/api/default/_search",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]
