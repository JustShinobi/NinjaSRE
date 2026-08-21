"""Azure SQL, end to end: capability, client, proxy, injection, vendor.

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
    "subscription": "00000000-0000-0000-0000-000000000000",
}


SESSION_STATISTICS: Final = IntegrationScenario(
    key="azure_sql-session-statistics",
    integration="azure_sql",
    capability="azure_sql_session_statistics",
    arguments={"scope": "", "start": "", "end": "", "group_by": "properties.state"},
    responses=(
        json_response(
            {
                "value": [
                    {"name": "sql-prod", "properties": {"state": "Ready"}},
                    {"name": "sql-staging", "properties": {"state": "Ready"}},
                    {"name": "sql-old", "properties": {"state": "Disabled"}},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 sessions across",
    expected_paths=(
        "/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.Sql/servers",
    ),
)


SLOW_QUERIES: Final = IntegrationScenario(
    key="azure_sql-slow-queries",
    integration="azure_sql",
    capability="azure_sql_slow_queries",
    arguments={"scope": "", "start": "", "end": "", "limit": 10},
    responses=(json_response({"value": [{"name": "sql-prod", "properties": {"state": "Ready"}}]}),),
    credential=CREDENTIAL,
    expected_summary="1 statements from Azure SQL",
    expected_paths=(
        "/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.Sql/servers",
    ),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (SESSION_STATISTICS, SLOW_QUERIES)

__all__ = ["CREDENTIAL", "SCENARIOS", "SESSION_STATISTICS", "SLOW_QUERIES"]
