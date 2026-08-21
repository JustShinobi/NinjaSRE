"""Railway, end to end: capability, client, proxy, injection, vendor.

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


PIPELINE_STATISTICS: Final = IntegrationScenario(
    key="railway-pipeline-statistics",
    integration="railway",
    capability="railway_pipeline_statistics",
    arguments={"project": "p-1", "start": "", "end": "", "group_by": "node.status"},
    responses=(
        json_response(
            {
                "data": {
                    "deployments": {
                        "edges": [
                            {"node": {"id": "d1", "status": "SUCCESS"}},
                            {"node": {"id": "d2", "status": "SUCCESS"}},
                            {"node": {"id": "d3", "status": "CRASHED"}},
                        ]
                    }
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 runs across",
    expected_paths=("/graphql/v2",),
)


FAILED_RUNS: Final = IntegrationScenario(
    key="railway-failed-runs",
    integration="railway",
    capability="railway_failed_runs",
    arguments={"project": "p-1", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "data": {
                    "deployments": {
                        "edges": [
                            {
                                "node": {
                                    "id": "d3",
                                    "status": "FAILED",
                                    "createdAt": "2026-08-07T11:50:00Z",
                                }
                            }
                        ]
                    }
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 runs from Railway",
    expected_paths=("/graphql/v2",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (PIPELINE_STATISTICS, FAILED_RUNS)

__all__ = ["CREDENTIAL", "SCENARIOS", "PIPELINE_STATISTICS", "FAILED_RUNS"]
