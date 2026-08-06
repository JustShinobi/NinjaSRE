"""AWS credentials, and the integration that proves the proxy was worth building.

Every other vendor attaches a token. AWS computes a signature over the whole
request, keyed by a chain derived from the secret access key — so a client that
signs is a client that holds a key, and AWS is the largest integration family an
SRE platform has. Leaving it in the client would make the most-used vendor the
one exception to Article IV, which is the same as not having Article IV.

So the client sends an unsigned request with a handle and the proxy signs it
(SC-006). The declaration below is what makes that a data change rather than a
code change: ``SignatureInjection(SigV4Signer(service=...))`` is one more entry
in the same list Datadog fills with headers, and the engine does not learn a
branch.

**Hosts are per-service and per-region**, which is a lot of them, so ``rule_for``
builds the allow-list from the services and regions a deployment actually uses.
An operator running CloudWatch in two regions gets two hosts permitted, not
every AWS endpoint that exists — which matters because "AWS" is not a trust
boundary, it is a very large surface.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.injection import InjectionRule, SignatureInjection
from platform.credentials.proxy.signing.sigv4 import SigV4Signer
from platform.credentials.schemas import CredentialField, CredentialSchema, FieldKind

INTEGRATION: Final = "aws"

#: The services an investigation reaches. Each has its own endpoint host per
#: region and its own SigV4 service name, and the two differ often enough that
#: mapping them is worth doing once here.
CLOUDWATCH_LOGS: Final = "logs"
CLOUDWATCH_MONITORING: Final = "monitoring"
EC2: Final = "ec2"

DEFAULT_SERVICES: Final[tuple[str, ...]] = (CLOUDWATCH_LOGS, CLOUDWATCH_MONITORING, EC2)
DEFAULT_REGION: Final = "us-east-1"

SCHEMA: Final = CredentialSchema(
    integration=INTEGRATION,
    fields=(
        CredentialField(
            name="access_key_id",
            description="AWS access key id, or the one an assumed role issued.",
            pattern=r"(AKIA|ASIA)[0-9A-Z]{16}",
        ),
        CredentialField(
            name="secret_access_key",
            description="The secret half of the key pair. Never leaves the proxy.",
            min_length=40,
        ),
        CredentialField(
            name="session_token",
            description="Session token, for temporary credentials from STS.",
            required=False,
        ),
        CredentialField(
            name="region",
            description="Default region for signing and endpoint selection.",
            kind=FieldKind.PUBLIC,
            required=False,
        ),
    ),
)


def host_for(service: str, region: str) -> str:
    """Return the regional endpoint host for one AWS service."""
    return f"{service}.{region}.amazonaws.com"


def rule_for(
    *,
    services: tuple[str, ...] = DEFAULT_SERVICES,
    regions: tuple[str, ...] = (DEFAULT_REGION,),
    signing_service: str = CLOUDWATCH_LOGS,
) -> InjectionRule:
    """Return the injection rule for the services and regions a deployment uses.

    ``signing_service`` is separate from ``services`` because SigV4's service
    name is part of the signing scope, and a rule signs for one. A deployment
    reaching two AWS services builds two clients on two rules rather than one
    rule that signs for whichever service it happened to be pointed at — which
    would produce signatures AWS rejects with a message that blames the key.
    """
    hosts = tuple(sorted({host_for(service, region) for service in services for region in regions}))
    return InjectionRule(
        integration=INTEGRATION,
        hosts=hosts,
        injections=(
            SignatureInjection(
                signer=SigV4Signer(service=signing_service, default_region=regions[0])
            ),
        ),
        #: STS-issued credentials expire, and the vault stores their expiry, so
        #: the refresh window and the single expiry retry both apply here.
        refreshable=True,
    )


DEFAULT_RULE: Final = rule_for()


__all__ = [
    "CLOUDWATCH_LOGS",
    "CLOUDWATCH_MONITORING",
    "DEFAULT_REGION",
    "DEFAULT_RULE",
    "DEFAULT_SERVICES",
    "EC2",
    "INTEGRATION",
    "SCHEMA",
    "host_for",
    "rule_for",
]
