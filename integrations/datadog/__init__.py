"""Datadog: logs, metrics, and monitors, with the keys at the network edge.

The reference integration for the ordinary case. Two header injections, six
regional hosts, no vendor SDK, and a client that knows the API and nothing about
authentication.

``DESCRIPTOR`` is what the catalogue-wide test walks. Every integration exposes
one, and exposing it is what makes "every integration routes through the proxy"
an assertion rather than an audit.
"""

from __future__ import annotations

from typing import Final

from integrations.datadog.client import DatadogClient
from integrations.datadog.config import HOSTS, INTEGRATION, RULE, SCHEMA, base_url
from integrations.datadog.verifier import DatadogVerifier
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

__all__ = [
    "DATADOG",
    "DESCRIPTOR",
    "HOSTS",
    "INTEGRATION",
    "RULE",
    "SCHEMA",
    "DatadogClient",
    "DatadogVerifier",
    "base_url",
]
