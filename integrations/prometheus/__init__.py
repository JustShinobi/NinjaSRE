"""Prometheus: PromQL evaluation and the alert rules currently firing, from the server that holds the series rather than from a dashboard on top of it.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.prometheus.client import PAGINATION, PrometheusClient
from integrations.prometheus.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.prometheus.verifier import PERMISSIONS, PrometheusVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=PrometheusVerifier(),
    client_class=PrometheusClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "There is no official Prometheus client for reading; the client libraries are for exposing metrics, not querying them. The query API is three endpoints."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.METRICS_STORE,
    summary="PromQL evaluation and the alert rules currently firing, from the server that holds the series rather than from a dashboard on top of it.",
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
    "PrometheusClient",
    "PrometheusVerifier",
    "base_url",
]
