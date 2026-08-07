"""groundcover, end to end: capability, client, proxy, injection, vendor.

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


METRIC_STATISTICS: Final = IntegrationScenario(
    key="groundcover-metric-statistics",
    integration="groundcover",
    capability="groundcover_metric_statistics",
    arguments={
        "query": "rate(http_requests_total[5m])",
        "start": "",
        "end": "",
        "group_by": "metric.workload",
    },
    responses=(
        json_response(
            {
                "data": {
                    "result": [
                        {"metric": {"workload": "checkout"}, "values": [[1754503600, "0.42"]]},
                        {"metric": {"workload": "payments"}, "values": [[1754503600, "0.01"]]},
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 series across",
    expected_paths=("/api/promql/query_range",),
)


ACTIVE_ALERTS: Final = IntegrationScenario(
    key="groundcover-active-alerts",
    integration="groundcover",
    capability="groundcover_active_alerts",
    arguments={"state": "firing", "start": "", "end": "", "limit": 10},
    responses=(json_response({"monitors": [{"title": "checkout latency", "state": "firing"}]}),),
    credential=CREDENTIAL,
    expected_summary="1 alerts from groundcover",
    expected_paths=("/api/monitors/list",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (METRIC_STATISTICS, ACTIVE_ALERTS)

__all__ = ["CREDENTIAL", "SCENARIOS", "METRIC_STATISTICS", "ACTIVE_ALERTS"]
