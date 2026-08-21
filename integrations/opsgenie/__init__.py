"""Opsgenie: Opsgenie alerts and their state: what is open, one alert's log, and the acknowledgement that stops the escalation.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.opsgenie.client import PAGINATION, OpsgenieClient
from integrations.opsgenie.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.opsgenie.verifier import PERMISSIONS, OpsgenieVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=OpsgenieVerifier(),
    client_class=OpsgenieClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor's Python client is a thin wrapper over the same REST API and adds nothing the base client does not already provide — retry, timeouts, structured errors, and bounded page walks. Writing the client directly also keeps a library that reads its key from the process environment out of the dependency tree entirely."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.INCIDENT_MANAGEMENT,
    summary="Opsgenie alerts and their state: what is open, one alert's log, and the acknowledgement that stops the escalation.",
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
    "OpsgenieClient",
    "OpsgenieVerifier",
    "base_url",
]
