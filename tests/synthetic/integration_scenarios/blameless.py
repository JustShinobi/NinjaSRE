"""Blameless, end to end: capability, client, proxy, injection, vendor.

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


INCIDENT_STATISTICS: Final = IntegrationScenario(
    key="blameless-incident-statistics",
    integration="blameless",
    capability="blameless_incident_statistics",
    arguments={"status": "active", "start": "", "end": "", "group_by": "severity"},
    responses=(
        json_response(
            {
                "incidents": [
                    {"id": "b1", "title": "checkout 5xx", "severity": "SEV1"},
                    {"id": "b2", "title": "cart errors", "severity": "SEV1"},
                    {"id": "b3", "title": "docs typo", "severity": "SEV3"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 incidents across",
    expected_paths=("/api/v1/incidents",),
)


INCIDENT_TIMELINE: Final = IntegrationScenario(
    key="blameless-incident-timeline",
    integration="blameless",
    capability="blameless_incident_timeline",
    arguments={"incident": "b1", "start": "", "end": "", "limit": 10},
    responses=(
        json_response({"incidents": [{"id": "b1", "title": "checkout 5xx", "severity": "SEV1"}]}),
    ),
    credential=CREDENTIAL,
    expected_summary="1 timeline entries from Blameless",
    expected_paths=("/api/v1/incidents",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (INCIDENT_STATISTICS, INCIDENT_TIMELINE)

__all__ = ["CREDENTIAL", "SCENARIOS", "INCIDENT_STATISTICS", "INCIDENT_TIMELINE"]
