"""Datadog: logs, metrics, and monitors, with the keys at the network edge.

The reference integration for the ordinary case. Two header injections, six
regional hosts, no vendor SDK, and a client that knows the API and nothing about
authentication.

Two declarations are what discovery walks for, and they answer different
questions. ``DESCRIPTOR`` is the credential half — what a credential is made of,
which hosts it may reach, how the secret enters a request, and how to check that
it works. ``PROFILE`` is the operational half — what class of system this is,
where it can be reached, what permissions its capabilities need, and how its
endpoints page.

Exposing both is what makes "every integration routes through the proxy" and
"every integration is at full parity" assertions rather than audits.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.datadog.client import PAGINATION, DatadogClient
from integrations.datadog.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.datadog.verifier import PERMISSIONS, DatadogVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DATADOG: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=DatadogVerifier(),
    client_class=DatadogClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The official SDK is a thin generated wrapper over a REST API, and everything it "
        "adds — retry, pagination, timeouts, structured errors — the base client already "
        "provides. Writing the client directly also keeps a library that reads DD_API_KEY "
        "from the environment out of the dependency tree entirely."
    ),
)

DESCRIPTOR: Final = DATADOG

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Datadog",
    category=IntegrationCategory.LOG_STORE,
    summary=(
        "Log search and aggregation, metric series, and monitor state, across Datadog's "
        "six regional deployments."
    ),
    regions=REGIONS,
    permissions=PERMISSIONS,
    pagination=PAGINATION,
)

__all__ = [
    "DATADOG",
    "DESCRIPTOR",
    "HOSTS",
    "INTEGRATION",
    "PAGINATION",
    "PERMISSIONS",
    "PROFILE",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "DatadogClient",
    "DatadogVerifier",
    "base_url",
]
