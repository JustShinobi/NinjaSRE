"""Jenkins, end to end: capability, client, proxy, injection, vendor.

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


PIPELINE_STATISTICS: Final = IntegrationScenario(
    key="jenkins-pipeline-statistics",
    integration="jenkins",
    capability="jenkins_pipeline_statistics",
    arguments={"project": "", "start": "", "end": "", "group_by": "color"},
    responses=(
        json_response(
            {
                "jobs": [
                    {"name": "checkout", "color": "blue"},
                    {"name": "payments", "color": "blue"},
                    {"name": "reports", "color": "red"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 runs across",
    expected_paths=("/api/json",),
)


FAILED_RUNS: Final = IntegrationScenario(
    key="jenkins-failed-runs",
    integration="jenkins",
    capability="jenkins_failed_runs",
    arguments={"project": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "jobs": [
                    {
                        "name": "reports",
                        "builds": [
                            {"number": 412, "result": "FAILURE", "timestamp": 1754503600000}
                        ],
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 runs from Jenkins",
    expected_paths=("/api/json",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (PIPELINE_STATISTICS, FAILED_RUNS)

__all__ = ["CREDENTIAL", "SCENARIOS", "PIPELINE_STATISTICS", "FAILED_RUNS"]
