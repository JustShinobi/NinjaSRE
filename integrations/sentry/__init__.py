"""Sentry: Application errors as Sentry groups them: which issues are open, how often each is firing, and the events behind the ones that matter.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.sentry.client import PAGINATION, SentryClient
from integrations.sentry.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.sentry.verifier import PERMISSIONS, SentryVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=SentryVerifier(),
    client_class=SentryClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The Sentry Python SDK is for sending events, not reading them. The read API is plain REST and is written directly."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.LOG_STORE,
    summary="Application errors as Sentry groups them: which issues are open, how often each is firing, and the events behind the ones that matter.",
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
    "SentryClient",
    "SentryVerifier",
    "base_url",
]
