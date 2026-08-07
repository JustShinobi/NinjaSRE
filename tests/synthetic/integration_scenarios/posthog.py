"""PostHog, end to end: capability, client, proxy, injection, vendor.

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
    "project_id": "1",
}


METRIC_STATISTICS: Final = IntegrationScenario(
    key="posthog-metric-statistics",
    integration="posthog",
    capability="posthog_metric_statistics",
    arguments={
        "query": "",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "group_by": "event",
    },
    responses=(
        json_response(
            {
                "results": [
                    {"event": "$pageview"},
                    {"event": "$pageview"},
                    {"event": "checkout_failed"},
                ],
                "next": None,
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 series across",
    expected_paths=("/api/projects/1/events/",),
)


ACTIVE_ALERTS: Final = IntegrationScenario(
    key="posthog-active-alerts",
    integration="posthog",
    capability="posthog_active_alerts",
    arguments={"state": "", "start": "", "end": "", "limit": 10},
    responses=(json_response({"results": [{"key": "new-cart", "active": True}], "next": None}),),
    credential=CREDENTIAL,
    expected_summary="1 alerts from PostHog",
    expected_paths=("/api/projects/1/feature_flags/",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (METRIC_STATISTICS, ACTIVE_ALERTS)

__all__ = ["CREDENTIAL", "SCENARIOS", "METRIC_STATISTICS", "ACTIVE_ALERTS"]
