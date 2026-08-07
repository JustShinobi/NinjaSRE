"""Grafana, end to end: capability, client, proxy, injection, vendor.

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


RESOURCE_INVENTORY: Final = IntegrationScenario(
    key="grafana-resource-inventory",
    integration="grafana",
    capability="grafana_resource_inventory",
    arguments={"kind": "checkout", "start": "", "end": "", "group_by": "type"},
    responses=(
        json_response(
            [
                {"uid": "abc", "title": "Checkout", "type": "dash-db"},
                {"uid": "def", "title": "Payments", "type": "dash-db"},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 resources across",
    expected_paths=("/api/search",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="grafana-recent-changes",
    integration="grafana",
    capability="grafana_recent_changes",
    arguments={"kind": "", "start": "1754500000000", "end": "1754503600000"},
    responses=(json_response([{"id": 41, "text": "deploy checkout 4.2.1", "type": "annotation"}]),),
    credential=CREDENTIAL,
    expected_summary="1 changes from Grafana",
    expected_paths=("/api/annotations",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
