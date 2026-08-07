"""Argo CD, end to end: capability, client, proxy, injection, vendor.

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
    key="argocd-pipeline-statistics",
    integration="argocd",
    capability="argocd_pipeline_statistics",
    arguments={"project": "default", "start": "", "end": "", "group_by": "status.sync.status"},
    responses=(
        json_response(
            {
                "items": [
                    {"metadata": {"name": "checkout"}, "status": {"sync": {"status": "Synced"}}},
                    {"metadata": {"name": "payments"}, "status": {"sync": {"status": "Synced"}}},
                    {"metadata": {"name": "reports"}, "status": {"sync": {"status": "OutOfSync"}}},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 runs across",
    expected_paths=("/api/v1/applications",),
)


FAILED_RUNS: Final = IntegrationScenario(
    key="argocd-failed-runs",
    integration="argocd",
    capability="argocd_failed_runs",
    arguments={"project": "default", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "items": [
                    {
                        "metadata": {"name": "reports"},
                        "status": {
                            "sync": {"status": "OutOfSync"},
                            "health": {"status": "Degraded"},
                        },
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 runs from Argo CD",
    expected_paths=("/api/v1/applications",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (PIPELINE_STATISTICS, FAILED_RUNS)

__all__ = ["CREDENTIAL", "SCENARIOS", "PIPELINE_STATISTICS", "FAILED_RUNS"]
