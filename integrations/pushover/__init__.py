"""Pushover: Pushover as a last-resort notification path: which delivery groups exist, and a finding pushed to a responder's device.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.pushover.client import PAGINATION, PushoverClient
from integrations.pushover.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.pushover.verifier import PERMISSIONS, PushoverVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=PushoverVerifier(),
    client_class=PushoverClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor's Python client is a thin wrapper over the same REST API and adds nothing the base client does not already provide — retry, timeouts, structured errors, and bounded page walks. Writing the client directly also keeps a library that reads its key from the process environment out of the dependency tree entirely."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Pushover",
    category=IntegrationCategory.COMMUNICATION,
    summary="Pushover as a last-resort notification path: which delivery groups exist, and a finding pushed to a responder's device.",
    where_to_get_it=(
        "Create an application at pushover.net → Your Applications for the API token, "
        "and copy the user or group key from your own Pushover account page."
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
    "PushoverClient",
    "PushoverVerifier",
    "base_url",
]
