"""VictoriaMetrics, end to end: capability, client, proxy, injection, vendor.

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


METRIC_STATISTICS: Final = IntegrationScenario(
    key="victoriametrics-metric-statistics",
    integration="victoriametrics",
    capability="victoriametrics_metric_statistics",
    arguments={
        "query": "rate(http_requests_total[5m])",
        "start": "",
        "end": "",
        "group_by": "metric.job",
    },
    responses=(
        json_response(
            {
                "data": {
                    "result": [
                        {"metric": {"job": "checkout"}, "values": [[1754503600, "0.42"]]},
                        {"metric": {"job": "payments"}, "values": []},
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 series across",
    expected_paths=("/api/v1/query_range",),
)


ACTIVE_ALERTS: Final = IntegrationScenario(
    key="victoriametrics-active-alerts",
    integration="victoriametrics",
    capability="victoriametrics_active_alerts",
    arguments={"state": "firing", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {"data": {"alerts": [{"labels": {"alertname": "HighErrorRate"}, "state": "firing"}]}}
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 alerts from VictoriaMetrics",
    expected_paths=("/api/v1/alerts",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (METRIC_STATISTICS, ACTIVE_ALERTS)

__all__ = ["CREDENTIAL", "SCENARIOS", "METRIC_STATISTICS", "ACTIVE_ALERTS"]
