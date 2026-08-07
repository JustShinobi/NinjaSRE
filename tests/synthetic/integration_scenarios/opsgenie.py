"""Opsgenie, end to end: capability, client, proxy, injection, vendor.

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
}


INCIDENT_STATISTICS: Final = IntegrationScenario(
    key="opsgenie-incident-statistics",
    integration="opsgenie",
    capability="opsgenie_incident_statistics",
    arguments={"status": "status:open", "start": "", "end": "", "group_by": "priority"},
    responses=(
        json_response(
            {
                "data": [
                    {"id": "a1", "message": "checkout 5xx", "priority": "P1"},
                    {"id": "a2", "message": "checkout latency", "priority": "P1"},
                    {"id": "a3", "message": "reports lag", "priority": "P3"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 incidents across",
    expected_paths=("/v2/alerts",),
)


INCIDENT_TIMELINE: Final = IntegrationScenario(
    key="opsgenie-incident-timeline",
    integration="opsgenie",
    capability="opsgenie_incident_timeline",
    arguments={"incident": "a1", "start": "", "end": "", "limit": 10},
    responses=(
        json_response({"data": [{"id": "a1", "message": "checkout 5xx", "status": "open"}]}),
    ),
    credential=CREDENTIAL,
    expected_summary="1 timeline entries from Opsgenie",
    expected_paths=("/v2/alerts",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (INCIDENT_STATISTICS, INCIDENT_TIMELINE)

__all__ = ["CREDENTIAL", "SCENARIOS", "INCIDENT_STATISTICS", "INCIDENT_TIMELINE"]
