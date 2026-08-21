"""Google Cloud, end to end: capability, client, proxy, injection, vendor.

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
    "project": "acme-production",
}


RESOURCE_INVENTORY: Final = IntegrationScenario(
    key="gcp-resource-inventory",
    integration="gcp",
    capability="gcp_resource_inventory",
    arguments={
        "kind": "compute.googleapis.com/Instance",
        "start": "",
        "end": "",
        "group_by": "assetType",
    },
    responses=(
        json_response(
            {
                "assets": [
                    {
                        "assetType": "compute.googleapis.com/Instance",
                        "name": "//compute/instances/checkout-1",
                    },
                    {
                        "assetType": "compute.googleapis.com/Instance",
                        "name": "//compute/instances/checkout-2",
                    },
                    {"assetType": "storage.googleapis.com/Bucket", "name": "//storage/acme-logs"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 resources across",
    expected_paths=("/v1/projects/acme-production/assets",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="gcp-recent-changes",
    integration="gcp",
    capability="gcp_recent_changes",
    arguments={"kind": "", "start": "", "end": "2026-08-07T12:00:00Z", "limit": 10},
    responses=(
        json_response(
            {
                "assets": [
                    {
                        "assetType": "compute.googleapis.com/Instance",
                        "name": "//compute/instances/checkout-1",
                        "updateTime": "2026-08-07T11:50:00Z",
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from Google Cloud",
    expected_paths=("/v1/projects/acme-production/assets",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
