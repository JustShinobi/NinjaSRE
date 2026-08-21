"""Google Docs: What the team has written in Google Docs: the documents matching a search, and the ones most recently modified.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.google_docs.client import PAGINATION, GoogleDocsClient
from integrations.google_docs.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.google_docs.verifier import PERMISSIONS, GoogleDocsVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=GoogleDocsVerifier(),
    client_class=GoogleDocsClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "google-api-python-client resolves credentials through Application Default Credentials, which reads the environment, a metadata server, and a well-known file — three places Article IV does not permit a credential to be."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.TICKETING,
    summary="What the team has written in Google Docs: the documents matching a search, and the ones most recently modified.",
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
    "GoogleDocsClient",
    "GoogleDocsVerifier",
    "base_url",
]
