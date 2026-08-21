"""AWS ECS, end to end: capability, client, proxy, injection, vendor.

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
    key="aws_ecs-resource-inventory",
    integration="aws_ecs",
    capability="aws_ecs_resource_inventory",
    arguments={"kind": "", "start": "", "end": "", "group_by": "cluster"},
    responses=(
        json_response(
            {
                "clusterArns": [
                    "arn:aws:ecs:us-east-1:1:cluster/prod",
                    "arn:aws:ecs:us-east-1:1:cluster/staging",
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 resources across",
    expected_paths=("/",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="aws_ecs-recent-changes",
    integration="aws_ecs",
    capability="aws_ecs_recent_changes",
    arguments={"kind": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {"taskDefinitionArns": ["arn:aws:ecs:us-east-1:1:task-definition/checkout:42"]}
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from AWS ECS",
    expected_paths=("/",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
