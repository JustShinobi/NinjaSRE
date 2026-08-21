"""MongoDB Atlas, end to end: capability, client, proxy, injection, vendor.

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
    "group": "5e2211c17a3e5a48f5497de3",
}


SESSION_STATISTICS: Final = IntegrationScenario(
    key="mongodb_atlas-session-statistics",
    integration="mongodb_atlas",
    capability="mongodb_atlas_session_statistics",
    arguments={"scope": "", "start": "", "end": "", "group_by": "typeName"},
    responses=(
        json_response(
            {
                "results": [
                    {"id": "p1", "typeName": "REPLICA_PRIMARY"},
                    {"id": "p2", "typeName": "REPLICA_SECONDARY"},
                    {"id": "p3", "typeName": "REPLICA_SECONDARY"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 sessions across",
    expected_paths=("/api/atlas/v2/groups/5e2211c17a3e5a48f5497de3/processes",),
)


SLOW_QUERIES: Final = IntegrationScenario(
    key="mongodb_atlas-slow-queries",
    integration="mongodb_atlas",
    capability="mongodb_atlas_slow_queries",
    arguments={"scope": "", "start": "", "end": "", "limit": 10},
    responses=(json_response({"results": [{"name": "checkout", "stateName": "IDLE"}]}),),
    credential=CREDENTIAL,
    expected_summary="1 statements from MongoDB Atlas",
    expected_paths=("/api/atlas/v2/groups/5e2211c17a3e5a48f5497de3/clusters",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (SESSION_STATISTICS, SLOW_QUERIES)

__all__ = ["CREDENTIAL", "SCENARIOS", "SESSION_STATISTICS", "SLOW_QUERIES"]
