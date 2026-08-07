"""AWS ECS: The ECS control plane: which clusters this account runs and which task definitions have been registered, which is where a deployment shows up.

AWS signs a request rather than attaching a token to it, so a client that signed would be a client that holds a key. This one sends the request unsigned and the proxy signs it at the network edge, which is why the largest integration family in the catalogue is not the one exception to Article IV.

Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.aws_ecs.client import PAGINATION, AwsEcsClient
from integrations.aws_ecs.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.aws_ecs.verifier import PERMISSIONS, AwsEcsVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=AwsEcsVerifier(),
    client_class=AwsEcsClient,
    sdk_strategy=SdkStrategy.PROXY_SIGNED,
    strategy_note=(
        "boto3 signs in-process and resolves credentials from the environment, an instance profile, or a shared file — three places Article IV does not permit a credential to be. The client sends an unsigned request and the proxy signs it, which is the proxy_signed row of the SDK table and the reason that row exists."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.CLOUD_CONTROL_PLANE,
    summary="The ECS control plane: which clusters this account runs and which task definitions have been registered, which is where a deployment shows up.",
    regions=REGIONS,
    permissions=PERMISSIONS,
    pagination=PAGINATION,
)

__all__ = [
    "DESCRIPTOR",
    "HOSTS",
    "INTEGRATION",
    "PAGINATION",
    "PERMISSIONS",
    "PROFILE",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "AwsEcsClient",
    "AwsEcsVerifier",
    "base_url",
]
