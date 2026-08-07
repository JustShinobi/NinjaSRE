"""Azure, end to end: capability, client, proxy, injection, vendor.

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
    "subscription": "00000000-0000-0000-0000-000000000000",
}


RESOURCE_INVENTORY: Final = IntegrationScenario(
    key="azure-resource-inventory",
    integration="azure",
    capability="azure_resource_inventory",
    arguments={"kind": "", "start": "", "end": "", "group_by": "type"},
    responses=(
        json_response(
            {
                "value": [
                    {"name": "checkout-vm", "type": "Microsoft.Compute/virtualMachines"},
                    {"name": "checkout-vm-2", "type": "Microsoft.Compute/virtualMachines"},
                    {"name": "acmelogs", "type": "Microsoft.Storage/storageAccounts"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 resources across",
    expected_paths=("/subscriptions/00000000-0000-0000-0000-000000000000/resources",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="azure-recent-changes",
    integration="azure",
    capability="azure_recent_changes",
    arguments={"kind": "", "start": "2026-08-07T11:00:00Z", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "value": [
                    {
                        "operationName": {
                            "value": "Microsoft.Compute/virtualMachines/restart/action"
                        },
                        "eventTimestamp": "2026-08-07T11:50:00Z",
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from Azure",
    expected_paths=(
        "/subscriptions/00000000-0000-0000-0000-000000000000/providers/microsoft.insights/eventtypes/management/values",
    ),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
