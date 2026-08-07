"""Redis Cloud, end to end: capability, client, proxy, injection, vendor.

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
    "secret_key": "ninjasre-scenario-second-000000",
}


SESSION_STATISTICS: Final = IntegrationScenario(
    key="redis-session-statistics",
    integration="redis",
    capability="redis_session_statistics",
    arguments={"scope": "", "start": "", "end": "", "group_by": "status"},
    responses=(
        json_response(
            {
                "subscriptions": [
                    {"id": 1, "name": "prod", "status": "active"},
                    {"id": 2, "name": "staging", "status": "active"},
                    {"id": 3, "name": "old", "status": "error"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 sessions across",
    expected_paths=("/v1/subscriptions",),
)


SLOW_QUERIES: Final = IntegrationScenario(
    key="redis-slow-queries",
    integration="redis",
    capability="redis_slow_queries",
    arguments={"scope": "", "start": "", "end": "", "limit": 10},
    responses=(json_response({"subscriptions": [{"id": 3, "name": "old", "status": "error"}]}),),
    credential=CREDENTIAL,
    expected_summary="1 statements from Redis Cloud",
    expected_paths=("/v1/subscriptions",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (SESSION_STATISTICS, SLOW_QUERIES)

__all__ = ["CREDENTIAL", "SCENARIOS", "SESSION_STATISTICS", "SLOW_QUERIES"]
