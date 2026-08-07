"""AWS Lambda, end to end: capability, client, proxy, injection, vendor.

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
    key="aws_lambda-resource-inventory",
    integration="aws_lambda",
    capability="aws_lambda_resource_inventory",
    arguments={"kind": "", "start": "", "end": "", "group_by": "Runtime"},
    responses=(
        json_response(
            {
                "Functions": [
                    {
                        "FunctionName": "checkout",
                        "Runtime": "python3.12",
                        "LastModified": "2026-08-07T11:20:00.000+0000",
                    },
                    {
                        "FunctionName": "reports",
                        "Runtime": "python3.12",
                        "LastModified": "2026-06-01T09:00:00.000+0000",
                    },
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 resources across",
    expected_paths=("/2015-03-31/functions/",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="aws_lambda-recent-changes",
    integration="aws_lambda",
    capability="aws_lambda_recent_changes",
    arguments={"kind": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "Functions": [
                    {"FunctionName": "checkout", "LastModified": "2026-08-07T11:20:00.000+0000"}
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from AWS Lambda",
    expected_paths=("/2015-03-31/functions/",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
