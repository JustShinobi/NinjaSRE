"""Snowflake: Snowflake over its SQL REST API: what is running in the account now, and the slowest statements the query history recorded.



Two declarations, and discovery walks for both. ``DESCRIPTOR`` is the credential
half — what a credential is made of, which hosts it may reach, how the secret
enters a request, and how to check that it works. ``PROFILE`` is the operational
half — what class of system this is, where it can be reached, what permissions
its capabilities need, and how its endpoints page.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.snowflake.client import PAGINATION, SnowflakeClient
from integrations.snowflake.schema import HOSTS, INTEGRATION, REGIONS, RULE, SCHEMA, base_url
from integrations.snowflake.verifier import PERMISSIONS, SnowflakeVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

DESCRIPTOR: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=SnowflakeVerifier(),
    client_class=SnowflakeClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The Snowflake connector holds a private key in process to sign its JWTs, which is exactly what the proxy exists to prevent. The SQL REST API takes an already issued token, so the signing stays on the proxy side."
    ),
)

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Snowflake",
    category=IntegrationCategory.DATABASE,
    summary="Snowflake over its SQL REST API: what is running in the account now, and the slowest statements the query history recorded.",
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
    "SnowflakeClient",
    "SnowflakeVerifier",
    "base_url",
]
