"""VictoriaLogs, end to end: capability, client, proxy, injection, vendor.

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
    key="victorialogs-log-statistics",
    integration="victorialogs",
    capability="victorialogs_log_statistics",
    arguments={"query": '_stream:{app="checkout"}', "start": "", "end": "", "group_by": "level"},
    responses=(
        json_response(
            [
                {"level": "error", "_msg": "oom"},
                {"level": "error", "_msg": "oom"},
                {"level": "info", "_msg": "ok"},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 log lines across",
    expected_paths=("/select/logsql/query",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="victorialogs-sample-logs",
    integration="victorialogs",
    capability="victorialogs_sample_logs",
    arguments={"query": '_stream:{app="checkout"} error', "start": "", "end": "", "limit": 5},
    responses=(json_response([{"level": "error", "_msg": "oom"}]),),
    credential=CREDENTIAL,
    expected_summary="1 log lines from VictoriaLogs",
    expected_paths=("/select/logsql/query",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]
