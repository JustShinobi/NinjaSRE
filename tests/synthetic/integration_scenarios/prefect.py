"""Prefect, end to end: capability, client, proxy, injection, vendor.

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
    key="prefect-pipeline-health",
    integration="prefect",
    capability="prefect_pipeline_health",
    arguments={"scope": "", "start": "", "end": "", "group_by": "state.type"},
    responses=(
        json_response(
            [
                {"id": "r1", "state": {"type": "COMPLETED"}},
                {"id": "r2", "state": {"type": "COMPLETED"}},
                {"id": "r3", "state": {"type": "FAILED"}},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 tasks across",
    expected_paths=("/api/flow_runs/filter",),
)


RECENT_FAILURES: Final = IntegrationScenario(
    key="prefect-recent-failures",
    integration="prefect",
    capability="prefect_recent_failures",
    arguments={"scope": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            [{"id": "r3", "state": {"type": "FAILED"}, "start_time": "2026-08-07T11:50:00Z"}]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 failures from Prefect",
    expected_paths=("/api/flow_runs/filter",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (PIPELINE_HEALTH, RECENT_FAILURES)

__all__ = ["CREDENTIAL", "SCENARIOS", "PIPELINE_HEALTH", "RECENT_FAILURES"]
