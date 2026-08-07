"""AWS CloudTrail, end to end: capability, client, proxy, injection, vendor.

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
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "region": "us-east-1",
}


RESOURCE_INVENTORY: Final = IntegrationScenario(
    key="aws_cloudtrail-resource-inventory",
    integration="aws_cloudtrail",
    capability="aws_cloudtrail_resource_inventory",
    arguments={
        "kind": "",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "group_by": "EventName",
    },
    responses=(
        json_response(
            {
                "Events": [
                    {
                        "EventName": "UpdateFunctionCode",
                        "Username": "deploy-role",
                        "EventTime": "2026-08-07T11:50:00Z",
                    },
                    {
                        "EventName": "UpdateFunctionCode",
                        "Username": "deploy-role",
                        "EventTime": "2026-08-07T11:20:00Z",
                    },
                    {
                        "EventName": "ModifyDBInstance",
                        "Username": "sre",
                        "EventTime": "2026-08-07T10:00:00Z",
                    },
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 resources across",
    expected_paths=("/",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="aws_cloudtrail-recent-changes",
    integration="aws_cloudtrail",
    capability="aws_cloudtrail_recent_changes",
    arguments={
        "kind": "",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "limit": 10,
    },
    responses=(
        json_response(
            {
                "Events": [
                    {
                        "EventName": "UpdateFunctionCode",
                        "Username": "deploy-role",
                        "EventTime": "2026-08-07T11:50:00Z",
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from AWS CloudTrail",
    expected_paths=("/",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
