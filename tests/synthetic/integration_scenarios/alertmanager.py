"""Alertmanager, end to end: capability, client, proxy, injection, vendor.

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
    key="alertmanager-incident-statistics",
    integration="alertmanager",
    capability="alertmanager_incident_statistics",
    arguments={"status": "", "start": "", "end": "", "group_by": "labels.alertname"},
    responses=(
        json_response(
            [
                {
                    "labels": {"alertname": "HighErrorRate", "severity": "critical"},
                    "status": {"state": "active"},
                },
                {
                    "labels": {"alertname": "HighErrorRate", "severity": "warning"},
                    "status": {"state": "active"},
                },
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 incidents across",
    expected_paths=("/api/v2/alerts",),
)


INCIDENT_TIMELINE: Final = IntegrationScenario(
    key="alertmanager-incident-timeline",
    integration="alertmanager",
    capability="alertmanager_incident_timeline",
    arguments={"incident": "HighErrorRate", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            [{"labels": {"alertname": "HighErrorRate"}, "receiver": {"name": "payments-oncall"}}]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 timeline entries from Alertmanager",
    expected_paths=("/api/v2/alerts/groups",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (INCIDENT_STATISTICS, INCIDENT_TIMELINE)

__all__ = ["CREDENTIAL", "SCENARIOS", "INCIDENT_STATISTICS", "INCIDENT_TIMELINE"]
