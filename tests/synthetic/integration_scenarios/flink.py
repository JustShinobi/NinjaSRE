"""Flink, end to end: capability, client, proxy, injection, vendor.

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
    key="flink-pipeline-health",
    integration="flink",
    capability="flink_pipeline_health",
    arguments={"scope": "", "start": "", "end": "", "group_by": "state"},
    responses=(
        json_response(
            {
                "jobs": [
                    {"jid": "j1", "name": "enrich", "state": "RUNNING"},
                    {"jid": "j2", "name": "aggregate", "state": "RUNNING"},
                    {"jid": "j3", "name": "export", "state": "RESTARTING"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 tasks across",
    expected_paths=("/jobs/overview",),
)


RECENT_FAILURES: Final = IntegrationScenario(
    key="flink-recent-failures",
    integration="flink",
    capability="flink_recent_failures",
    arguments={"scope": "", "start": "", "end": "", "limit": 10},
    responses=(json_response({"jobs": [{"jid": "j3", "name": "export", "state": "RESTARTING"}]}),),
    credential=CREDENTIAL,
    expected_summary="1 failures from Flink",
    expected_paths=("/jobs/overview",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (PIPELINE_HEALTH, RECENT_FAILURES)

__all__ = ["CREDENTIAL", "SCENARIOS", "PIPELINE_HEALTH", "RECENT_FAILURES"]
