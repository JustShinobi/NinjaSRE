"""SigNoz: SigNoz's span store: where latency and errors concentrate for a service, and the slowest traces behind that concentration.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.signoz.client import PAGINATION, SignozClient
from integrations.signoz.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.signoz.verifier import PERMISSIONS, SignozVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=SignozVerifier(),
    client_class=SignozClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor's Python client is a thin wrapper over the same REST API and adds nothing the base client does not already provide — retry, timeouts, structured errors, and bounded page walks. Writing the client directly also keeps a library that reads its key from the process environment out of the dependency tree entirely."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="SigNoz",
    category=IntegrationCategory.TRACING,
    summary="SigNoz's span store: where latency and errors concentrate for a service, and the slowest traces behind that concentration.",
    where_to_get_it=(
        "SigNoz → Settings → API keys issues a workspace API key; self-hosted SigNoz is "
        "reached at the address its query service answers on."
    ),
    regions=REGIONS,
    permissions=PERMISSIONS,
    pagination=PAGINATION,
    # the port SigNoz's query service serves on, which is the API rather than the UI.
    default_port=8080,
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
    "SignozClient",
    "SignozVerifier",
    "base_url",
]
