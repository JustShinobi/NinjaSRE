"""OpenObserve: SQL search over OpenObserve streams, counted by field before any record is read, for the estates that chose it for its storage cost.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.openobserve.client import PAGINATION, OpenobserveClient
from integrations.openobserve.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.openobserve.verifier import PERMISSIONS, OpenobserveVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=OpenobserveVerifier(),
    client_class=OpenobserveClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor's Python client is a thin wrapper over the same REST API and adds nothing the base client does not already provide — retry, timeouts, structured errors, and bounded page walks. Writing the client directly also keeps a library that reads its key from the process environment out of the dependency tree entirely."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="OpenObserve",
    category=IntegrationCategory.LOG_STORE,
    summary="SQL search over OpenObserve streams, counted by field before any record is read, for the estates that chose it for its storage cost.",
    regions=REGIONS,
    permissions=PERMISSIONS,
    pagination=PAGINATION,
    # the port a default OpenObserve serves its API and UI on.
    default_port=5080,
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
    "OpenobserveClient",
    "OpenobserveVerifier",
    "base_url",
]
