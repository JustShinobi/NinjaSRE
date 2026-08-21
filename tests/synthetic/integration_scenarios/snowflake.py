"""Snowflake, end to end: capability, client, proxy, injection, vendor.

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
    "account": "acme-prod",
    "warehouse": "reporting_wh",
}


SESSION_STATISTICS: Final = IntegrationScenario(
    key="snowflake-session-statistics",
    integration="snowflake",
    capability="snowflake_session_statistics",
    arguments={"scope": "", "start": "", "end": "", "group_by": "EXECUTION_STATUS"},
    responses=(
        json_response(
            {
                "resultSetMetaData": {
                    "rowType": [
                        {"name": "QUERY_ID"},
                        {"name": "USER_NAME"},
                        {"name": "EXECUTION_STATUS"},
                    ]
                },
                "data": [
                    ["q1", "reports", "RUNNING"],
                    ["q2", "reports", "RUNNING"],
                    ["q3", "app", "BLOCKED"],
                ],
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 sessions across",
    expected_paths=("/api/v2/statements",),
)


SLOW_QUERIES: Final = IntegrationScenario(
    key="snowflake-slow-queries",
    integration="snowflake",
    capability="snowflake_slow_queries",
    arguments={"scope": "", "start": "", "end": "", "limit": 5},
    responses=(
        json_response(
            {
                "resultSetMetaData": {
                    "rowType": [{"name": "QUERY_TEXT"}, {"name": "TOTAL_ELAPSED_TIME"}]
                },
                "data": [["SELECT * FROM events", 42100]],
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 statements from Snowflake",
    expected_paths=("/api/v2/statements",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (SESSION_STATISTICS, SLOW_QUERIES)

__all__ = ["CREDENTIAL", "SCENARIOS", "SESSION_STATISTICS", "SLOW_QUERIES"]
