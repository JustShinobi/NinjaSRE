"""BigQuery: BigQuery job state for a project: what is running or queued, and the jobs that took longest, which is where a data-freshness incident usually starts.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.bigquery.client import PAGINATION, BigqueryClient
from integrations.bigquery.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.bigquery.verifier import PERMISSIONS, BigqueryVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=BigqueryVerifier(),
    client_class=BigqueryClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "google-cloud-bigquery resolves credentials through Application Default Credentials, which reads the environment, a metadata server, and a well-known file — three places Article IV does not permit a credential to be."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.DATABASE,
    summary="BigQuery job state for a project: what is running or queued, and the jobs that took longest, which is where a data-freshness incident usually starts.",
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
    "BigqueryClient",
    "BigqueryVerifier",
    "base_url",
]
