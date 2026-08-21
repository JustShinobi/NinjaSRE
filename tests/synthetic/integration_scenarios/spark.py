"""Spark, end to end: capability, client, proxy, injection, vendor.

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


PIPELINE_HEALTH: Final = IntegrationScenario(
    key="spark-pipeline-health",
    integration="spark",
    capability="spark_pipeline_health",
    arguments={"scope": "running", "start": "", "end": "", "group_by": "attempts.completed"},
    responses=(
        json_response(
            [
                {"id": "app-1", "name": "rollup", "attempts": [{"completed": True}]},
                {"id": "app-2", "name": "rollup", "attempts": [{"completed": True}]},
                {"id": "app-3", "name": "ingest", "attempts": [{"completed": False}]},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 tasks across",
    expected_paths=("/api/v1/applications",),
)


RECENT_FAILURES: Final = IntegrationScenario(
    key="spark-recent-failures",
    integration="spark",
    capability="spark_recent_failures",
    arguments={"scope": "", "start": "2026-08-07T11:00:00.000GMT", "end": "", "limit": 10},
    responses=(
        json_response([{"id": "app-3", "name": "ingest", "attempts": [{"completed": False}]}]),
    ),
    credential=CREDENTIAL,
    expected_summary="1 failures from Spark",
    expected_paths=("/api/v1/applications",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (PIPELINE_HEALTH, RECENT_FAILURES)

__all__ = ["CREDENTIAL", "SCENARIOS", "PIPELINE_HEALTH", "RECENT_FAILURES"]
