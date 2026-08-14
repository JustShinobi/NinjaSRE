"""Elasticsearch: Search over Elasticsearch indices, counted by field before any document is read, for the deployments whose logs live there rather than in a hosted log product.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.elasticsearch.client import PAGINATION, ElasticsearchClient
from integrations.elasticsearch.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.elasticsearch.verifier import PERMISSIONS, ElasticsearchVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=ElasticsearchVerifier(),
    client_class=ElasticsearchClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The official client insists on constructing its own transport and reads ELASTIC_PASSWORD and cloud ids from the environment. The search API is one POST, so the client is written directly rather than fought with."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Elasticsearch",
    category=IntegrationCategory.LOG_STORE,
    summary="Search over Elasticsearch indices, counted by field before any document is read, for the deployments whose logs live there rather than in a hosted log product.",
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
    "ElasticsearchClient",
    "ElasticsearchVerifier",
    "base_url",
]
