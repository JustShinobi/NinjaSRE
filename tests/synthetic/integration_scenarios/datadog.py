"""Datadog, end to end: capability, client, proxy, injection, vendor.

Two scenarios, chosen for what would break silently. The first is the
aggregation shape — Datadog buries counts three levels down in
``data.buckets[].computes.c0``, and a rename anywhere in that path turns every
statistic into zero without raising. The second is the cursor walk, which is
where a pagination change stops an investigation at the first page while still
answering.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

CREDENTIAL: Final[dict[str, str]] = {
    "api_key": "0123456789abcdef0123456789abcdef",
    "app_key": "0123456789abcdef0123456789abcdef01234567",
}

LOG_STATISTICS: Final = IntegrationScenario(
    key="datadog-log-statistics",
    integration="datadog",
    capability="datadog_log_statistics",
    arguments={
        "query": "service:checkout",
        "start": "now-1h",
        "end": "now",
        "group_by": "status",
    },
    responses=(
        json_response(
            {
                "data": {
                    "buckets": [
                        {"by": {"status": "error"}, "computes": {"c0": 412}},
                        {"by": {"status": "info"}, "computes": {"c0": 38_104}},
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="38516 logs matched",
    expected_paths=("/api/v2/logs/analytics/aggregate",),
)

SAMPLE_LOGS: Final = IntegrationScenario(
    key="datadog-sample-logs",
    integration="datadog",
    capability="datadog_sample_logs",
    arguments={
        "query": "service:checkout status:error",
        "start": "now-1h",
        "end": "now",
        "limit": 2,
    },
    responses=(
        json_response(
            {
                "data": [
                    {
                        "attributes": {
                            "message": "cart serialiser out of memory",
                            "service": "checkout",
                            "status": "error",
                            "timestamp": "2026-08-07T11:52:11Z",
                        }
                    }
                ],
                "meta": {"page": {"after": "cursor-2"}},
            }
        ),
        json_response(
            {
                "data": [
                    {
                        "attributes": {
                            "message": "cart serialiser out of memory",
                            "service": "checkout",
                            "status": "error",
                            "timestamp": "2026-08-07T11:52:14Z",
                        }
                    }
                ],
                "meta": {"page": {}},
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 log lines matching",
    expected_paths=("/api/v2/logs/events/search", "/api/v2/logs/events/search"),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "LOG_STATISTICS", "SAMPLE_LOGS", "SCENARIOS"]
