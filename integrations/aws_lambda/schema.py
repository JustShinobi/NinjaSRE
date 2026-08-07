"""AWS Lambda's credential shape, hosts, and how its secret enters a request.

Three declarations, each preventing one failure. The schema is what an operator
is prompted for, and a field they were never asked for is a credential that half
works. The region map is the egress allow-list — one tuple rather than two,
because two drift. The injection rule is how the secret is added at the network
edge, and every field it reads is one the schema declares.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import RegionMap
from integrations._base.schema import credential_schema, public, secret
from platform.credentials.proxy.injection import InjectionRule, SignatureInjection
from platform.credentials.proxy.signing.sigv4 import SigV4Signer

INTEGRATION: Final = "aws_lambda"
DEFAULT_REGION: Final = "us-east-1"

#: Every host AWS Lambda serves its API from. Exact names, no wildcards.
REGIONS: Final = RegionMap.from_template(
    INTEGRATION,
    template="lambda.{region}.amazonaws.com",
    names=(
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "eu-west-1",
        "eu-west-2",
        "eu-central-1",
        "ap-south-1",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-northeast-1",
        "sa-east-1",
    ),
    default="us-east-1",
)

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    secret(
        "access_key_id",
        "AWS access key id, or the one an assumed role issued",
        pattern=r"(AKIA|ASIA)[0-9A-Z]{16}",
    ),
    secret(
        "secret_access_key",
        "The secret half of the key pair. Never leaves the proxy",
        min_length=40,
    ),
    secret("session_token", "Session token, for temporary credentials from STS", required=False),
    public("region", "Default region for signing and endpoint selection"),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(
        SignatureInjection(signer=SigV4Signer(service="lambda", default_region=DEFAULT_REGION)),
    ),
)


def base_url(region: str = "") -> str:
    """Return the API base URL for a region, or for the default one."""
    return REGIONS.base_url(region)


__all__ = [
    "DEFAULT_REGION",
    "HOSTS",
    "INTEGRATION",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "base_url",
]
