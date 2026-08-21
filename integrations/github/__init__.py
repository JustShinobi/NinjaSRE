"""GitHub: What landed in a repository and when: the commits on its default branch and the pull requests recently merged into it.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.github.client import PAGINATION, GithubClient
from integrations.github.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.github.verifier import PERMISSIONS, GithubVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=GithubVerifier(),
    client_class=GithubClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "PyGithub is synchronous and builds its own transport; the REST API is plain and well documented, so the client is written directly."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="GitHub",
    category=IntegrationCategory.VERSION_CONTROL,
    summary="What landed in a repository and when: the commits on its default branch and the pull requests recently merged into it.",
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
    "GithubClient",
    "GithubVerifier",
    "base_url",
]
