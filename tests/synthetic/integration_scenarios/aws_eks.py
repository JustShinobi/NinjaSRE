"""AWS EKS, end to end: capability, client, proxy, injection, vendor.

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
    key="aws_eks-resource-inventory",
    integration="aws_eks",
    capability="aws_eks_resource_inventory",
    arguments={"kind": "", "start": "", "end": "", "group_by": "cluster"},
    responses=(json_response({"clusters": ["prod", "staging"]}),),
    credential=CREDENTIAL,
    expected_summary="2 resources across",
    expected_paths=("/clusters",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="aws_eks-recent-changes",
    integration="aws_eks",
    capability="aws_eks_recent_changes",
    arguments={"kind": "", "start": "", "end": "", "limit": 10},
    responses=(json_response({"clusters": ["prod"]}),),
    credential=CREDENTIAL,
    expected_summary="1 changes from AWS EKS",
    expected_paths=("/clusters",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
