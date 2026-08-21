"""New Relic, end to end: capability, client, proxy, injection, vendor.

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
    "account": "1234567",
}


METRIC_STATISTICS: Final = IntegrationScenario(
    key="new_relic-metric-statistics",
    integration="new_relic",
    capability="new_relic_metric_statistics",
    arguments={"query": "", "start": "", "end": "", "group_by": "health_status"},
    responses=(
        json_response(
            {
                "applications": [
                    {"name": "checkout", "health_status": "red"},
                    {"name": "payments", "health_status": "green"},
                    {"name": "reports", "health_status": "green"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 series across",
    expected_paths=("/v2/applications.json",),
)


ACTIVE_ALERTS: Final = IntegrationScenario(
    key="new_relic-active-alerts",
    integration="new_relic",
    capability="new_relic_active_alerts",
    arguments={"state": "open", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "violations": [
                    {"label": "High error rate", "priority": "critical", "opened_at": 1754503600000}
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 alerts from New Relic",
    expected_paths=("/v2/alerts_violations.json",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (METRIC_STATISTICS, ACTIVE_ALERTS)

__all__ = ["CREDENTIAL", "SCENARIOS", "METRIC_STATISTICS", "ACTIVE_ALERTS"]
