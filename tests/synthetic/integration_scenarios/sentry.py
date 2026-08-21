"""Sentry, end to end: capability, client, proxy, injection, vendor.

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
    "organisation": "acme",
    "project": "checkout",
}


LOG_STATISTICS: Final = IntegrationScenario(
    key="sentry-log-statistics",
    integration="sentry",
    capability="sentry_log_statistics",
    arguments={"query": "is:unresolved", "start": "", "end": "", "group_by": "level"},
    responses=(
        json_response(
            [
                {"id": "1", "title": "OutOfMemory", "level": "error", "count": "412"},
                {"id": "2", "title": "TimeoutError", "level": "error", "count": "38"},
                {"id": "3", "title": "Deprecation", "level": "warning", "count": "4"},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 log lines across",
    expected_paths=("/api/0/organizations/acme/issues/",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="sentry-sample-logs",
    integration="sentry",
    capability="sentry_sample_logs",
    arguments={"query": "is:unresolved level:error", "start": "", "end": "", "limit": 5},
    responses=(
        json_response([{"id": "1", "title": "OutOfMemory", "level": "error", "count": "412"}]),
    ),
    credential=CREDENTIAL,
    expected_summary="1 log lines from Sentry",
    expected_paths=("/api/0/organizations/acme/issues/",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]
