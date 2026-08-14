"""FireHydrant: FireHydrant's incident record: what is active, one incident's events, and the note that says an automated investigation has started.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.firehydrant.client import PAGINATION, FirehydrantClient
from integrations.firehydrant.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.firehydrant.verifier import PERMISSIONS, FirehydrantVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=FirehydrantVerifier(),
    client_class=FirehydrantClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor's Python client is a thin wrapper over the same REST API and adds nothing the base client does not already provide — retry, timeouts, structured errors, and bounded page walks. Writing the client directly also keeps a library that reads its key from the process environment out of the dependency tree entirely."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="FireHydrant",
    category=IntegrationCategory.INCIDENT_MANAGEMENT,
    summary="FireHydrant's incident record: what is active, one incident's events, and the note that says an automated investigation has started.",
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
    "FirehydrantClient",
    "FirehydrantVerifier",
    "base_url",
]
