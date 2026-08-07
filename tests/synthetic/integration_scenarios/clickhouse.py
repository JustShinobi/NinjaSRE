"""ClickHouse, end to end: capability, client, proxy, injection, vendor.

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
    "username": "ninjasre-scenario",
    "password": "ninjasre-scenario-secret",
}


SESSION_STATISTICS: Final = IntegrationScenario(
    key="clickhouse-session-statistics",
    integration="clickhouse",
    capability="clickhouse_session_statistics",
    arguments={"scope": "", "start": "", "end": "", "group_by": "user"},
    responses=(
        json_response(
            {
                "data": [
                    {"query_id": "q1", "user": "reports", "elapsed": 42.1},
                    {"query_id": "q2", "user": "reports", "elapsed": 3.2},
                    {"query_id": "q3", "user": "app", "elapsed": 0.1},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 sessions across",
    expected_paths=("/",),
)


SLOW_QUERIES: Final = IntegrationScenario(
    key="clickhouse-slow-queries",
    integration="clickhouse",
    capability="clickhouse_slow_queries",
    arguments={"scope": "", "start": "", "end": "", "limit": 5},
    responses=(
        json_response(
            {
                "data": [
                    {
                        "query": "SELECT * FROM events",
                        "query_duration_ms": 42100,
                        "type": "QueryFinish",
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 statements from ClickHouse",
    expected_paths=("/",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (SESSION_STATISTICS, SLOW_QUERIES)

__all__ = ["CREDENTIAL", "SCENARIOS", "SESSION_STATISTICS", "SLOW_QUERIES"]
