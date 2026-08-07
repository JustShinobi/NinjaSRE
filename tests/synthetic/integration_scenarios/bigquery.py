"""BigQuery, end to end: capability, client, proxy, injection, vendor.

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
    "project": "acme-production",
}


SESSION_STATISTICS: Final = IntegrationScenario(
    key="bigquery-session-statistics",
    integration="bigquery",
    capability="bigquery_session_statistics",
    arguments={"scope": "", "start": "", "end": "", "group_by": "status.state"},
    responses=(
        json_response(
            {
                "jobs": [
                    {"id": "j1", "status": {"state": "DONE"}},
                    {"id": "j2", "status": {"state": "DONE"}},
                    {"id": "j3", "status": {"state": "RUNNING"}},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 sessions across",
    expected_paths=("/bigquery/v2/projects/acme-production/jobs",),
)


SLOW_QUERIES: Final = IntegrationScenario(
    key="bigquery-slow-queries",
    integration="bigquery",
    capability="bigquery_slow_queries",
    arguments={"scope": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "jobs": [
                    {
                        "id": "j3",
                        "status": {"state": "RUNNING"},
                        "statistics": {"startTime": "1754503600000"},
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 statements from BigQuery",
    expected_paths=("/bigquery/v2/projects/acme-production/jobs",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (SESSION_STATISTICS, SLOW_QUERIES)

__all__ = ["CREDENTIAL", "SCENARIOS", "SESSION_STATISTICS", "SLOW_QUERIES"]
