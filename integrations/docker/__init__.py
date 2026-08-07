"""Docker: The Docker Engine API: which containers exist and in what state, and the engine events that changed them.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.docker.client import PAGINATION, DockerClient
from integrations.docker.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.docker.verifier import PERMISSIONS, DockerVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=DockerVerifier(),
    client_class=DockerClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "docker-py opens a Unix socket or a TLS connection of its own and holds the client certificate in process. The Engine API is plain HTTP, so the client is written directly and the proxy holds whatever the fronting layer needs."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.CLOUD_CONTROL_PLANE,
    summary="The Docker Engine API: which containers exist and in what state, and the engine events that changed them.",
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
    "DockerClient",
    "DockerVerifier",
    "base_url",
]
