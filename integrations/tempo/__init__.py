"""Tempo: TraceQL against Grafana Tempo: which traces match a latency or error condition, and the slowest of them, for estates storing traces in object storage.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.tempo.client import PAGINATION, TempoClient
from integrations.tempo.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.tempo.verifier import PERMISSIONS, TempoVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=TempoVerifier(),
    client_class=TempoClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor's Python client is a thin wrapper over the same REST API and adds nothing the base client does not already provide — retry, timeouts, structured errors, and bounded page walks. Writing the client directly also keeps a library that reads its key from the process environment out of the dependency tree entirely."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Tempo",
    category=IntegrationCategory.TRACING,
    summary="TraceQL against Grafana Tempo: which traces match a latency or error condition, and the slowest of them, for estates storing traces in object storage.",
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
    "TempoClient",
    "TempoVerifier",
    "base_url",
]
