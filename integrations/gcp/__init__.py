"""Google Cloud: The Google Cloud control plane through Cloud Asset Inventory and Cloud Logging: what exists in a project, and the admin activity that changed it.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.gcp.client import PAGINATION, GcpClient
from integrations.gcp.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.gcp.verifier import PERMISSIONS, GcpVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=GcpVerifier(),
    client_class=GcpClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "google-cloud-* resolves credentials through Application Default Credentials, which reads the environment, a metadata server, and a well-known file. All three are places Article IV does not permit a credential to be."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Google Cloud",
    category=IntegrationCategory.CLOUD_CONTROL_PLANE,
    summary="The Google Cloud control plane through Cloud Asset Inventory and Cloud Logging: what exists in a project, and the admin activity that changed it.",
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
    "GcpClient",
    "GcpVerifier",
    "base_url",
]
