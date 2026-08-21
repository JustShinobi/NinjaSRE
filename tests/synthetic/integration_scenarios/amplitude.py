"""Amplitude, end to end: capability, client, proxy, injection, vendor.

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


METRIC_STATISTICS: Final = IntegrationScenario(
    key="amplitude-metric-statistics",
    integration="amplitude",
    capability="amplitude_metric_statistics",
    arguments={
        "query": '{"event_type":"Checkout Completed"}',
        "start": "20260807",
        "end": "20260807",
        "group_by": "series",
    },
    responses=(
        json_response({"data": {"seriesLabels": ["Checkout Completed", "Checkout Started"]}}),
    ),
    credential=CREDENTIAL,
    expected_summary="2 series across",
    expected_paths=("/api/2/events/segmentation",),
)


ACTIVE_ALERTS: Final = IntegrationScenario(
    key="amplitude-active-alerts",
    integration="amplitude",
    capability="amplitude_active_alerts",
    arguments={"state": "", "start": "", "end": "", "limit": 10},
    responses=(json_response({"data": [{"label": "release 4.2.1", "date": "2026-08-07"}]}),),
    credential=CREDENTIAL,
    expected_summary="1 alerts from Amplitude",
    expected_paths=("/api/2/annotations",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (METRIC_STATISTICS, ACTIVE_ALERTS)

__all__ = ["CREDENTIAL", "SCENARIOS", "METRIC_STATISTICS", "ACTIVE_ALERTS"]
