"""Hermes: Hermes log tailing and classification: what a stream is currently emitting, grouped by the class its own model assigned.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.hermes.client import PAGINATION, HermesClient
from integrations.hermes.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.hermes.verifier import PERMISSIONS, HermesVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=HermesVerifier(),
    client_class=HermesClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor's Python client is a thin wrapper over the same REST API and adds nothing the base client does not already provide — retry, timeouts, structured errors, and bounded page walks. Writing the client directly also keeps a library that reads its key from the process environment out of the dependency tree entirely."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Hermes",
    category=IntegrationCategory.LOG_STORE,
    summary="Hermes log tailing and classification: what a stream is currently emitting, grouped by the class its own model assigned.",
    where_to_get_it=(
        "Hermes is this deployment's own log tailer; issue an access token from its own "
        "console under Access tokens."
    ),
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
    "HermesClient",
    "HermesVerifier",
    "base_url",
]
