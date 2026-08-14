"""Alertmanager: What Prometheus Alertmanager is currently holding: which alerts are firing, how they are grouped, and which are silenced rather than resolved.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.alertmanager.client import PAGINATION, AlertmanagerClient
from integrations.alertmanager.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.alertmanager.verifier import PERMISSIONS, AlertmanagerVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=AlertmanagerVerifier(),
    client_class=AlertmanagerClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The generated OpenAPI client for Alertmanager is unmaintained and brings a transport of its own. Three endpoints are written directly instead."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Alertmanager",
    category=IntegrationCategory.INCIDENT_MANAGEMENT,
    summary="What Prometheus Alertmanager is currently holding: which alerts are firing, how they are grouped, and which are silenced rather than resolved.",
    regions=REGIONS,
    permissions=PERMISSIONS,
    pagination=PAGINATION,
    # the port a default Alertmanager serves its API on.
    default_port=9093,
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
    "AlertmanagerClient",
    "AlertmanagerVerifier",
    "base_url",
]
