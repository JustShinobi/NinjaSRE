"""Microsoft Teams: The Teams channel an incident is being run from: what has been said, and a finding posted where the responders are.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.microsoft_teams.client import PAGINATION, MicrosoftTeamsClient
from integrations.microsoft_teams.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.microsoft_teams.verifier import PERMISSIONS, MicrosoftTeamsVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=MicrosoftTeamsVerifier(),
    client_class=MicrosoftTeamsClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor's Python client is a thin wrapper over the same REST API and adds nothing the base client does not already provide — retry, timeouts, structured errors, and bounded page walks. Writing the client directly also keeps a library that reads its key from the process environment out of the dependency tree entirely."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.COMMUNICATION,
    summary="The Teams channel an incident is being run from: what has been said, and a finding posted where the responders are.",
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
    "MicrosoftTeamsClient",
    "MicrosoftTeamsVerifier",
    "base_url",
]
