"""ServiceNow, end to end: capability, client, proxy, injection, vendor.

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


INCIDENT_STATISTICS: Final = IntegrationScenario(
    key="servicenow-incident-statistics",
    integration="servicenow",
    capability="servicenow_incident_statistics",
    arguments={"status": "active=true", "start": "", "end": "", "group_by": "priority"},
    responses=(
        json_response(
            {
                "result": [
                    {
                        "number": "INC001",
                        "short_description": "checkout 5xx",
                        "priority": "1 - Critical",
                    },
                    {
                        "number": "INC002",
                        "short_description": "cart errors",
                        "priority": "1 - Critical",
                    },
                    {"number": "INC003", "short_description": "printer", "priority": "4 - Low"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 incidents across",
    expected_paths=("/api/now/table/incident",),
)


INCIDENT_TIMELINE: Final = IntegrationScenario(
    key="servicenow-incident-timeline",
    integration="servicenow",
    capability="servicenow_incident_timeline",
    arguments={"incident": "INC001", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "result": [
                    {
                        "number": "INC001",
                        "short_description": "checkout 5xx",
                        "priority": "1 - Critical",
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 timeline entries from ServiceNow",
    expected_paths=("/api/now/table/incident",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (INCIDENT_STATISTICS, INCIDENT_TIMELINE)

__all__ = ["CREDENTIAL", "SCENARIOS", "INCIDENT_STATISTICS", "INCIDENT_TIMELINE"]
