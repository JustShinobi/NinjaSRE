"""Splunk: SPL search against Splunk, counted before it is read, for the estates whose logs have been in Splunk longer than the services producing them.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.splunk.client import PAGINATION, SplunkClient
from integrations.splunk.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.splunk.verifier import PERMISSIONS, SplunkVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=SplunkVerifier(),
    client_class=SplunkClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "splunk-sdk is synchronous, builds its own HTTP layer, and reads a session key it manages itself. Two endpoints are written directly instead."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Splunk",
    category=IntegrationCategory.LOG_STORE,
    summary="SPL search against Splunk, counted before it is read, for the estates whose logs have been in Splunk longer than the services producing them.",
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
    "SplunkClient",
    "SplunkVerifier",
    "base_url",
]
