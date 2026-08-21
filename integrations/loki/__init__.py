"""Loki: Log search over Loki's label index and LogQL, with the shape of a query counted before any line of it is read.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.loki.client import PAGINATION, LokiClient
from integrations.loki.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.loki.verifier import PERMISSIONS, LokiVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=LokiVerifier(),
    client_class=LokiClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "Loki ships no first-party Python client. The HTTP API is small and stable, and the base client already provides the retry, timeout, and error mapping any wrapper would have."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Grafana Loki",
    category=IntegrationCategory.LOG_STORE,
    summary="Log search over Loki's label index and LogQL, with the shape of a query counted before any line of it is read.",
    regions=REGIONS,
    permissions=PERMISSIONS,
    pagination=PAGINATION,
    # the port a default Loki serves its API on.
    default_port=3100,
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
    "LokiClient",
    "LokiVerifier",
    "base_url",
]
