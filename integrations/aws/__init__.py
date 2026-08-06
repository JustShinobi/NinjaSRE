"""AWS: CloudWatch reads, signed by the proxy, with no key in this process.

The reference integration for FR-018's ``PROXY_SIGNED`` row, and the one that
justifies the whole feature. SigV4 needs the secret at request-construction
time, so a signing client is a key-holding client — and AWS being the exception
would make Article IV meaningless, because AWS is where most of the calls go.

``DESCRIPTOR`` carries a rule for CloudWatch Logs in one region, which is what a
default deployment gets. A deployment reaching more services or regions builds
its rule with ``config.rule_for(...)`` at composition; SigV4's service name is
part of the signing scope, so one rule signs for one service.
"""

from __future__ import annotations

from typing import Final

from integrations.aws.client import CloudWatchLogsClient
from integrations.aws.config import (
    DEFAULT_REGION,
    DEFAULT_RULE,
    DEFAULT_SERVICES,
    INTEGRATION,
    SCHEMA,
    host_for,
    rule_for,
)
from integrations.aws.verifier import AwsVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

AWS: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=DEFAULT_RULE,
    verifier=AwsVerifier(),
    client_class=CloudWatchLogsClient,
    sdk_strategy=SdkStrategy.PROXY_SIGNED,
    strategy_note=(
        "The SDK constructs and signs requests internally with an in-process key, and "
        "there is no configuration that separates the two. So the client sends an "
        "unsigned request carrying a handle and the proxy performs SigV4 at the edge "
        "(SC-006). This is the case the mandatory proxy exists for: AWS is the largest "
        "integration family, and an exception here would be an exception everywhere."
    ),
)

DESCRIPTOR: Final = AWS

__all__ = [
    "AWS",
    "DEFAULT_REGION",
    "DEFAULT_RULE",
    "DEFAULT_SERVICES",
    "DESCRIPTOR",
    "INTEGRATION",
    "SCHEMA",
    "AwsVerifier",
    "CloudWatchLogsClient",
    "host_for",
    "rule_for",
]
