"""Grafana: What Grafana knows about a stack: which dashboards and folders exist, and the annotation timeline of deploys, alert state changes, and anything else a human marked.

Grafana is catalogued as a control plane rather than a metrics store on purpose. The series live in the datasources behind it — Prometheus, Loki, Mimir — and each of those is its own integration. What Grafana itself contributes to an investigation is the inventory and the annotation history, which is exactly what the control-plane methodology is about.

Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.grafana.client import PAGINATION, GrafanaClient
from integrations.grafana.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.grafana.verifier import PERMISSIONS, GrafanaVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=GrafanaVerifier(),
    client_class=GrafanaClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "Grafana's Python client is a thin generated wrapper over the same REST API and adds nothing the base client does not already provide. Writing the client directly also keeps a library that reads GRAFANA_API_KEY from the environment out of the dependency tree."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Grafana",
    category=IntegrationCategory.CLOUD_CONTROL_PLANE,
    summary="What Grafana knows about a stack: which dashboards and folders exist, and the annotation timeline of deploys, alert state changes, and anything else a human marked.",
    where_to_get_it=(
        "Create a service account token from Grafana's own Administration → Service "
        "accounts screen, with the Viewer role."
    ),
    regions=REGIONS,
    permissions=PERMISSIONS,
    pagination=PAGINATION,
    # the port a default Grafana serves on.
    default_port=3000,
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
    "GrafanaClient",
    "GrafanaVerifier",
    "base_url",
]
